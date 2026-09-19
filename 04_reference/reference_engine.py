"""Synthetic, normalized-input reference only; NOT production freight software.
No file parsing, persistence, identity verification, host integration or payment.
Usage: python 04_reference/reference_engine.py 03_examples/normalized-groups.json
"""
from __future__ import annotations
import hashlib
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

LIMIT = 10**12

class InputError(ValueError):
    """A normalized input violates the reference arithmetic contract."""

def bounded_int(value: Any, low: int = -LIMIT, high: int = LIMIT) -> int:
    if type(value) is not int or not low <= value <= high:
        raise InputError('Expected a bounded integer, never a bool/float.')
    return value

def yuan_to_minor(text: str) -> int:
    """Strict import boundary: no floating input, exponent or inferred rounding."""
    import re
    if type(text) is not str or re.fullmatch(r'-?(0|[1-9][0-9]*)(\.[0-9]{1,2})?', text) is None:
        raise InputError('Use an explicit decimal string with at most 2 places.')
    try:
        return bounded_int(int(Decimal(text) * 100))
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise InputError('Invalid or out-of-range money.') from exc

def canonical_hash(value: Any) -> str:
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def instant(text: str) -> datetime:
    try:
        d=datetime.fromisoformat(text.replace('Z','+00:00'))
    except (TypeError, ValueError, AttributeError) as exc:
        raise InputError('Invalid ISO timestamp.') from exc
    if d.tzinfo is None or d.utcoffset() is None:
        raise InputError('Explicit timezone required.')
    return d

def calculate_wait(elapsed: int, free: int, block: int, rate: int) -> int:
    e=bounded_int(elapsed,0,31536000)
    f=bounded_int(free,0,31536000)
    b=bounded_int(block,1,31536000)
    r=bounded_int(rate,0)
    return bounded_int(((max(0,e-f)+b-1)//b)*r,0)

def reconcile_group(g: dict[str,Any]) -> dict[str,Any]:
    if g.get('schema_version')!='0.1.0': raise InputError('Unsupported schema version.')
    lines=g['bill_lines']
    if not lines: raise InputError('At least one bill line is required.')
    ids=[b['line_id'] for b in lines]
    if len(ids)!=len(set(ids)): raise InputError('A source line cannot be consumed twice.')
    for b in lines: bounded_int(b['amount_minor'])
    billed=bounded_int(sum(b['amount_minor'] for b in lines))
    issues=[]
    refs=set(g.get('source_refs',[])) | {b['source_ref'] for b in lines}
    trace=[]
    r={'schema_version':'0.1.0','group_id':g['group_id'],'comparison_status':'NOT_COMPARABLE',
       'evidence_status':'COMPLETE','billed_minor':billed,'expected_minor':None,'delta_minor':None,
       'rule_ref':None,'issues':issues,'trace':trace,'source_refs':[]}
    def finish(code: str|None=None):
        if code: issues.append(code)
        r['issues']=sorted(set(issues));r['source_refs']=sorted(refs)
        r['result_digest']=canonical_hash(r)
        return r
    if g.get('pod_state')=='MISSING':
        r['evidence_status']='MISSING';issues.append('MISSING_POD')
    elif g.get('pod_state')=='CONFLICT':
        r['evidence_status']='CONFLICT';issues.append('POD_CONFLICT')
    if g.get('currency')!='CNY': return finish('CURRENCY_UNSUPPORTED')
    if g.get('match_state') not in ('EXACT','CONFIRMED') or not g.get('trip_id'):
        return finish(g.get('match_state') if g.get('match_state') in ('UNMATCHED','AMBIGUOUS','CONFLICT') else 'UNMATCHED')
    if g.get('trip_status')!='EXECUTED': return finish('TRIP_NOT_EXECUTED')
    # Explicit current-group credit links only. This is not a historical reconciliation.
    byid={b['line_id']:b for b in lines};credits={}
    for b in lines:
        amount=b['amount_minor'];target=b.get('reversal_of')
        if amount<0:
            orig=byid.get(target)
            if orig is None or orig['amount_minor']<=0 or orig.get('reversal_of') is not None:
                return finish('REVERSAL_INVALID')
            credits[target]=credits.get(target,0)-amount
        elif target is not None:
            return finish('REVERSAL_INVALID')
    if any(v>byid[k]['amount_minor'] for k,v in credits.items()): return finish('REVERSAL_INVALID')
    if billed<0: return finish('REVERSAL_INVALID')
    when=instant(g['service_time']);scoped=[]
    for rule in g['rules']:
        start,end=instant(rule['effective_from']),instant(rule['effective_to'])
        if end<=start: raise InputError('Empty or reversed rule interval.')
        if all(rule[k]==g[k] for k in ('workspace_id','carrier_id','route_id','vehicle_class','charge_code')) and start<=when<end:
            scoped.append(rule)
    if not scoped: return finish('RATE_NOT_FOUND')
    if len(scoped)!=1: return finish('RATE_AMBIGUOUS')
    rule=scoped[0]
    if rule.get('confirmed') is not True or not rule.get('confirmation_ref'): return finish('RULE_UNCONFIRMED')
    r['rule_ref']=f"{rule['rule_id']}@{rule['version']}";refs.update(rule['source_refs'])
    if rule['currency']!=g['currency'] or rule['amount_basis']!=g['amount_basis']:
        return finish('BASIS_MISMATCH')
    formula=rule['formula'];event=g['event'];refs.update(event.get('source_refs',[]))
    allowed={'BASE':'PER_TRIP','WAIT':'WAIT_BLOCKS','TOLL':'ACTUAL_RECEIPT'}
    if allowed.get(g['charge_code'])!=formula: return finish('UNSUPPORTED_FORMULA')
    if formula=='PER_TRIP':
        expected=bounded_int(rule['rate_minor'],0);trace.append(f'PER_TRIP: 1 * {expected} = {expected}')
    elif formula=='WAIT_BLOCKS':
        if event.get('elapsed_seconds') is None or event.get('time_evidence_verified') is not True:
            r['evidence_status']='MISSING';return finish('WAIT_EVIDENCE_INVALID')
        expected=calculate_wait(event['elapsed_seconds'],rule['free_seconds'],rule['block_seconds'],rule['rate_minor'])
        trace.append(f"WAIT_BLOCKS: ceil(max(0,{event['elapsed_seconds']}-{rule['free_seconds']})/{rule['block_seconds']}) * {rule['rate_minor']} = {expected}")
    elif formula=='ACTUAL_RECEIPT':
        if event.get('receipt_minor') is None or event.get('receipt_verified') is not True:
            r['evidence_status']='MISSING';return finish('MISSING_RECEIPT')
        receipt=bounded_int(event['receipt_minor'],0)
        cap=rule.get('cap_minor')
        expected=receipt if cap is None else min(receipt,bounded_int(cap,0))
        trace.append(f'ACTUAL_RECEIPT: receipt={receipt}, cap={cap}, expected={expected}')
    else: return finish('UNSUPPORTED_FORMULA')
    delta=bounded_int(billed-expected)
    r.update(comparison_status='COMPARABLE',expected_minor=expected,delta_minor=delta)
    trace.append(f'DELTA: {billed} - {expected} = {delta}')
    if delta>0: issues.append('AMOUNT_HIGH')
    elif delta<0: issues.append('AMOUNT_LOW')
    # Two positive charges with one allowed occurrence are a candidate, never proof.
    if len([b for b in lines if b['amount_minor']>0 and b.get('reversal_of') is None])>1:
        issues.append('DUPLICATE_SUSPECT')
    return finish()

def reconcile_all(groups: list[dict[str,Any]]) -> dict[str,Any]:
    seen_groups=set();seen_lines=set();scopes=set()
    for g in groups:
        if g['group_id'] in seen_groups: raise InputError('Duplicate group id.')
        seen_groups.add(g['group_id']);scopes.add((g['workspace_id'],g['carrier_id'],g['currency'],g['amount_basis']))
        for b in g['bill_lines']:
            if b['line_id'] in seen_lines: raise InputError('Source line assigned to more than one group.')
            seen_lines.add(b['line_id'])
    if len(scopes)>1: raise InputError('One reference batch requires one workspace/carrier/currency/bill basis.')
    results=[reconcile_group(g) for g in groups]
    s={k:0 for k in ('bill_line_count','group_count','comparable_line_count','comparable_group_count',
        'source_signed_total_minor','comparable_billed_minor','expected_comparable_minor','unresolved_billed_minor',
        'positive_difference_minor','negative_difference_minor','net_difference_minor',
        'abs_total_billed_minor','abs_comparable_billed_minor')}
    for g,r in zip(groups,results):
        s['group_count']+=1;s['bill_line_count']+=len(g['bill_lines'])
        s['source_signed_total_minor']+=r['billed_minor']
        absval=sum(abs(b['amount_minor']) for b in g['bill_lines'])
        s['abs_total_billed_minor']+=absval
        if r['comparison_status']=='COMPARABLE':
            s['comparable_group_count']+=1;s['comparable_line_count']+=len(g['bill_lines'])
            s['comparable_billed_minor']+=r['billed_minor'];s['expected_comparable_minor']+=r['expected_minor']
            s['abs_comparable_billed_minor']+=absval
            s['positive_difference_minor']+=max(r['delta_minor'],0)
            s['negative_difference_minor']+=min(r['delta_minor'],0)
        else: s['unresolved_billed_minor']+=r['billed_minor']
    s['net_difference_minor']=s['positive_difference_minor']+s['negative_difference_minor']
    for k,v in s.items(): bounded_int(v)
    assert s['source_signed_total_minor']==s['comparable_billed_minor']+s['unresolved_billed_minor']
    assert s['comparable_billed_minor']-s['expected_comparable_minor']==s['net_difference_minor']
    return {'reference_only':True,'summary':s,'results':results}

if __name__=='__main__':
    if len(sys.argv)!=2:
        raise SystemExit('Usage: reference_engine.py normalized-groups.json')
    with open(sys.argv[1],encoding='utf-8') as f: data=json.load(f)
    print(json.dumps(reconcile_all(data),ensure_ascii=False,indent=2,allow_nan=False))
