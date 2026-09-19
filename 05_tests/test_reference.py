"""Tests of design contracts and synthetic reference ONLY, not product acceptance."""
from pathlib import Path
import copy, json, sys, unittest
from datetime import datetime
from jsonschema import Draft202012Validator, FormatChecker

# HANDOFF_DELTA fix 1: fail fast when date-time format checking is not strict.
# jsonschema only registers the 'date-time' checker when rfc3339-validator is importable;
# without it, naive timestamps pass format validation silently (schema patterns still block
# them, but the check must not be assumed). See 06_development/HANDOFF_DELTA.md.
if 'date-time' not in FormatChecker().checkers:
    raise SystemExit('FATAL: date-time format checking is not strict. '
                     'Install 05_tests/requirements-reference.txt (rfc3339-validator).')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'04_reference'))
from reference_engine import reconcile_group, reconcile_all, calculate_wait, yuan_to_minor, InputError

def load(name):return json.loads((ROOT/name).read_text(encoding='utf-8'))
GROUPS=load('03_examples/normalized-groups.json')
GOLD=load('03_examples/golden-expectations.json')

class ReferenceTests(unittest.TestCase):
    def g(self,i=0):return copy.deepcopy(GROUPS[i])
    def issue(self,g,code):
        r=reconcile_group(g);self.assertIn(code,r['issues']);self.assertIsNone(r['delta_minor']);return r
    def test_summary_matches_independent_golden(self):
        self.assertEqual(reconcile_all(GROUPS)['summary'],load('03_examples/golden-summary.json'))
    def test_order_invariance(self):
        a=reconcile_all(GROUPS);b=reconcile_all(list(reversed(GROUPS)))
        self.assertEqual(a['summary'],b['summary'])
        self.assertEqual({x['group_id']:x['result_digest'] for x in a['results']},{x['group_id']:x['result_digest'] for x in b['results']})
    def test_repeat_deterministic(self):self.assertEqual(reconcile_all(GROUPS),reconcile_all(GROUPS))
    def test_line_order_invariance(self):
        g=self.g(8);a=reconcile_group(g);g['bill_lines'].reverse();self.assertEqual(a,reconcile_group(g))
    def test_wait_free_exact(self):self.assertEqual(calculate_wait(7200,7200,1800,5000),0)
    def test_wait_below_free(self):self.assertEqual(calculate_wait(7199,7200,1800,5000),0)
    def test_wait_one_second(self):self.assertEqual(calculate_wait(7201,7200,1800,5000),5000)
    def test_wait_one_exact_block(self):self.assertEqual(calculate_wait(9000,7200,1800,5000),5000)
    def test_wait_one_block_one_second(self):self.assertEqual(calculate_wait(9001,7200,1800,5000),10000)
    def test_wait_zero_block_rejected(self):
        with self.assertRaises(InputError):calculate_wait(9000,7200,0,5000)
    def test_wait_negative_rejected(self):
        with self.assertRaises(InputError):calculate_wait(-1,0,1800,5000)
    def test_wait_bool_rejected(self):
        with self.assertRaises(InputError):calculate_wait(True,0,1800,5000)
    def test_money_decimal_string(self):self.assertEqual(yuan_to_minor('1050.09'),105009)
    def test_money_negative(self):self.assertEqual(yuan_to_minor('-100.50'),-10050)
    def test_money_float_rejected(self):
        with self.assertRaises(InputError):yuan_to_minor(0.1)
    def test_money_three_decimals_rejected(self):
        with self.assertRaises(InputError):yuan_to_minor('1.001')
    def test_money_exponent_rejected(self):
        with self.assertRaises(InputError):yuan_to_minor('1e3')
    def test_money_nan_rejected(self):
        with self.assertRaises(InputError):yuan_to_minor('NaN')
    def test_money_limit_rejected(self):
        with self.assertRaises(InputError):yuan_to_minor('10000000000.01')
    def test_duplicate_id_rejected(self):
        g=self.g();g['bill_lines'].append(copy.deepcopy(g['bill_lines'][0]))
        with self.assertRaises(InputError):reconcile_group(g)
    def test_one_line_two_groups_rejected(self):
        a=self.g();b=self.g(1);b['bill_lines'][0]['line_id']=a['bill_lines'][0]['line_id']
        with self.assertRaises(InputError):reconcile_all([a,b])
    def test_mixed_workspace_rejected(self):
        a=self.g();b=self.g(1);b['workspace_id']='OTHER'
        with self.assertRaises(InputError):reconcile_all([a,b])
    def test_mixed_bill_basis_rejected(self):
        a=self.g();b=self.g(1);b['amount_basis']='NET'
        with self.assertRaises(InputError):reconcile_all([a,b])
    def test_bill_float_rejected(self):
        g=self.g();g['bill_lines'][0]['amount_minor']=1.0
        with self.assertRaises(InputError):reconcile_group(g)
    def test_bill_bool_rejected(self):
        g=self.g();g['bill_lines'][0]['amount_minor']=True
        with self.assertRaises(InputError):reconcile_group(g)
    def test_rate_start_inclusive(self):
        g=self.g();g['service_time']=g['rules'][0]['effective_from'];self.assertEqual(reconcile_group(g)['expected_minor'],100000)
    def test_rate_end_exclusive(self):
        g=self.g();g['service_time']=g['rules'][0]['effective_to'];self.issue(g,'RATE_NOT_FOUND')
    def test_rate_overlap_blocks(self):
        g=self.g();g['rules'].append(copy.deepcopy(g['rules'][0]));self.issue(g,'RATE_AMBIGUOUS')
    def test_rate_unconfirmed_blocks(self):
        g=self.g();g['rules'][0]['confirmed']=False;self.issue(g,'RULE_UNCONFIRMED')
    def test_rate_wrong_route_blocks(self):
        g=self.g();g['rules'][0]['route_id']='OTHER';self.issue(g,'RATE_NOT_FOUND')
    def test_timestamp_naive_rejected(self):
        g=self.g();g['service_time']='2026-09-01T08:00:00'
        with self.assertRaises(InputError):reconcile_group(g)
    def test_credit_orphan_blocks(self):
        g=self.g(8);g['bill_lines'][1]['reversal_of']='NO-LINE';self.issue(g,'REVERSAL_INVALID')
    def test_credit_excess_blocks(self):
        g=self.g(8);g['bill_lines'][1]['amount_minor']=-120001;self.issue(g,'REVERSAL_INVALID')
    def test_positive_credit_ref_blocks(self):
        g=self.g(8);g['bill_lines'][1]['amount_minor']=10000;self.issue(g,'REVERSAL_INVALID')
    def test_receipt_zero_verified_is_zero(self):
        g=self.g(4);g['event'].update(receipt_minor=0,receipt_verified=True);self.assertEqual(reconcile_group(g)['expected_minor'],0)
    def test_receipt_cap(self):
        g=self.g(4);g['event'].update(receipt_minor=9000,receipt_verified=True);g['rules'][0]['cap_minor']=8000
        self.assertEqual(reconcile_group(g)['expected_minor'],8000)
    def test_receipt_missing_not_zero(self):
        g=self.g(4);r=self.issue(g,'MISSING_RECEIPT');self.assertEqual(r['billed_minor'],8000)
    def test_pod_missing_not_passed(self):
        r=reconcile_group(self.g(7));self.assertEqual(r['delta_minor'],0);self.assertEqual(r['evidence_status'],'MISSING')
    def test_cancelled_trip_blocks(self):
        g=self.g();g['trip_status']='CANCELLED';self.issue(g,'TRIP_NOT_EXECUTED')
    def test_unknown_basis_blocks(self):
        g=self.g();g['amount_basis']='UNKNOWN';self.issue(g,'BASIS_MISMATCH')
    def test_formula_mismatch_blocks(self):
        g=self.g();g['rules'][0]['formula']='WAIT_BLOCKS';self.issue(g,'UNSUPPORTED_FORMULA')
    def test_wait_evidence_missing(self):
        g=self.g(2);g['event']['time_evidence_verified']=False;self.issue(g,'WAIT_EVIDENCE_INVALID')
    def test_duplicate_tags_not_double_counted(self):
        b=reconcile_all([self.g(3)]);self.assertEqual(b['summary']['positive_difference_minor'],150000)
    def test_schema_rejects_unknown_group_field(self):
        g=self.g();g['invented_permission']=True
        v=Draft202012Validator(load('02_contracts/charge-group-input.schema.json'),format_checker=FormatChecker())
        self.assertFalse(v.is_valid(g))
    def test_schema_rejects_non_cny(self):
        g=self.g();g['currency']='USD'
        v=Draft202012Validator(load('02_contracts/charge-group-input.schema.json'),format_checker=FormatChecker())
        self.assertFalse(v.is_valid(g))
    def test_schema_rejects_false_comparability(self):
        r=reconcile_group(self.g());r['comparison_status']='NOT_COMPARABLE'
        v=Draft202012Validator(load('02_contracts/reconciliation-result.schema.json'))
        self.assertFalse(v.is_valid(r))

# Each synthetic group and each contract example is counted as a separate test.
# HANDOFF_DELTA fix 2: generated tests are built by factory functions so no `test`
# function leaks into module scope; pytest previously collected it and errored
# on `fixture 'self' not found`. Count must stay 64 under both runners.
def _make_golden_test(i,e):
    def test(self):
        r=reconcile_group(self.g(i))
        self.assertEqual({k:r[k] for k in e},e)
    return test
for i,e in enumerate(GOLD):
    setattr(ReferenceTests,'test_golden_'+e['group_id'],_make_golden_test(i,e))
def _make_schema_test(path):
    def test(self):
        sch=json.loads(path.read_text());Draft202012Validator.check_schema(sch)
        example=load('03_examples/'+path.name.replace('.schema.json','.example.json'))
        Draft202012Validator(sch,format_checker=FormatChecker()).validate(example)
    return test
for path in sorted((ROOT/'02_contracts').glob('*.schema.json')):
    setattr(ReferenceTests,'test_schema_'+path.stem.replace('.','_').replace('-','_'),_make_schema_test(path))

def run():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ReferenceTests)
    res=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'scope':'design schemas + normalized synthetic reference only','run_at':datetime.now().astimezone().isoformat(),
            'tests_run':res.testsRun,'failures':len(res.failures),'errors':len(res.errors),'skipped':len(res.skipped),
            'status':'PASS' if res.wasSuccessful() else 'FAIL','production_acceptance':'NOT_RUN','workbuddy_host_test':'NOT_RUN','real_customer_trial':'NOT_RUN'}
    if '--write-report' in sys.argv:
        (ROOT/'08_verification/reference-test-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return res.wasSuccessful()
if __name__=='__main__':raise SystemExit(0 if run() else 1)
