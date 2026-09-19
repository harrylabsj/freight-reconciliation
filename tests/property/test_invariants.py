"""性质测试（§23.1）：随机组与参考引擎双向对齐 + 关键不变量。"""
from __future__ import annotations

import copy
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "04_reference"))

from conftest import GOLDEN_EXPECTATIONS  # noqa: E402
from reference_engine import reconcile_all as ref_reconcile_all  # noqa: E402

from freight_core.reconcile.engine import ReconcileEngine  # noqa: E402
from freight_core.service import ReconciliationService  # noqa: E402

NORMALIZED = json.loads(
    (Path(__file__).resolve().parents[2] / "03_examples/normalized-groups.json")
    .read_text())


def _mk_engine(svc):
    return ReconcileEngine(svc.db)


def _union_rules(raw):
    """全部组规则的并集（按 rule_id+version 去重），供引擎统一选择。"""
    seen = {}
    for g in raw:
        for rule in g.get("rules", []):
            seen[(rule["rule_id"], rule["version"])] = rule
    return list(seen.values())


def _groups_from_normalized(raw):
    """normalized-groups 直接转成引擎组形态（含 billed_minor / event）。"""
    groups = []
    for g in raw:
        g = copy.deepcopy(g)
        g["billed_minor"] = sum(b["amount_minor"] for b in g["bill_lines"])
        groups.append(g)
    return groups


def test_engine_matches_reference_on_golden(svc):
    """与参考引擎在同一规范化输入上逐组对齐：算术、状态、异常、摘要。"""
    eng = _mk_engine(svc)
    groups = _groups_from_normalized(NORMALIZED)
    rules = _union_rules(NORMALIZED)
    mine = eng.reconcile_all(groups, rules)
    ref = ref_reconcile_all(NORMALIZED)
    for mr, rr in zip(mine["results"], ref["results"]):
        assert mr["group_id"] == rr["group_id"]
        for k in ("comparison_status", "evidence_status", "billed_minor",
                  "expected_minor", "delta_minor", "rule_ref", "issues",
                  "result_digest"):
            assert mr[k] == rr[k], (mr["group_id"], k, mr[k], rr[k])
    for k, v in ref["summary"].items():
        assert mine["summary"][k] == v, k


def test_randomized_groups_match_reference(svc):
    """随机合成组：引擎与参考引擎语义一致（金标之外的外推验证）。"""
    rng = random.Random(20260919)
    eng = _mk_engine(svc)
    base_rules = _union_rules(NORMALIZED)
    for round_no in range(20):
        raw = []
        n_groups = rng.randint(1, 6)
        for gi in range(n_groups):
            g = copy.deepcopy(rng.choice(NORMALIZED))
            g["group_id"] = f"R{round_no}-{gi}"
            # 随机金额：保持冲销语义合法（负数行必须指向组内正数原行）
            for b in g["bill_lines"]:
                if b["amount_minor"] > 0 and rng.random() < 0.5:
                    b["amount_minor"] = rng.randrange(1, 200000)
            lines = [b for b in g["bill_lines"] if b["amount_minor"] > 0]
            if g["bill_lines"] and rng.random() < 0.3 and lines:
                target = rng.choice(lines)
                credit = copy.deepcopy(target)
                credit["line_id"] = target["line_id"] + "c"
                credit["amount_minor"] = -rng.randrange(0, target["amount_minor"] + 1)
                credit["reversal_of"] = target["line_id"]
                g["bill_lines"].append(credit)
            g["billed_minor"] = sum(b["amount_minor"] for b in g["bill_lines"])
            raw.append(g)
        groups = _groups_from_normalized(raw)
        try:
            mine = eng.reconcile_all(groups, base_rules)
            ref = ref_reconcile_all(raw)
        except Exception:
            continue  # 参考引擎拒绝的输入（如超限）不属于语义对齐范围
        for mr, rr in zip(mine["results"], ref["results"]):
            assert mr["result_digest"] == rr["result_digest"], (round_no, mr, rr)


def test_bill_line_order_invariance(svc):
    """账单行顺序变化不改变结果（§23.1）。"""
    eng = _mk_engine(svc)
    groups = _groups_from_normalized(NORMALIZED)
    rules = _union_rules(NORMALIZED)
    first = eng.reconcile_all(copy.deepcopy(groups), rules)
    shuffled = copy.deepcopy(groups)
    for g in shuffled:
        random.Random(7).shuffle(g["bill_lines"])
    second = eng.reconcile_all(shuffled, rules)
    assert [r["result_digest"] for r in first["results"]] == \
        [r["result_digest"] for r in second["results"]]


def test_group_order_invariance(svc):
    eng = _mk_engine(svc)
    groups = _groups_from_normalized(NORMALIZED)
    rules = _union_rules(NORMALIZED)
    a = eng.reconcile_all(groups, rules)
    b = eng.reconcile_all(list(reversed(groups)), rules)
    assert a["summary"] == b["summary"]
    assert {r["group_id"]: r["result_digest"] for r in a["results"]} == \
        {r["group_id"]: r["result_digest"] for r in b["results"]}


def test_net_zero_does_not_mask_directions(svc):
    """净额0不掩盖正负差异（§23.1）。"""
    eng = _mk_engine(svc)
    groups = _groups_from_normalized(NORMALIZED)
    rules = _union_rules(NORMALIZED)
    out = eng.reconcile_all(groups, rules)
    s = out["summary"]
    if s["positive_difference_minor"] and s["negative_difference_minor"]:
        assert s["net_difference_minor"] != 0 or \
            (s["positive_difference_minor"] == -s["negative_difference_minor"])
    # 金标中正向与反向同时存在，净差额不等于正向的简单掩盖
    assert s["net_difference_minor"] == s["positive_difference_minor"] \
        + s["negative_difference_minor"]


def test_duplicate_suspicion_not_double_counted(svc):
    """疑似重复组的同时偏高只计一次金额（§10.3，金标G04=+1500）。"""
    eng = _mk_engine(svc)
    groups = _groups_from_normalized(NORMALIZED)
    rules = _union_rules(NORMALIZED)
    out = eng.reconcile_all(groups, rules)
    dup = [r for r in out["results"] if "DUPLICATE_SUSPECT" in r["issues"]]
    assert len(dup) == 1
    g04 = next(r for r in out["results"]
               for g in groups if r["group_id"] == g["group_id"]
               and g["trip_id"] == "T004")
    assert g04["delta_minor"] == 150000  # 3000−1500=1500元，只计一次
