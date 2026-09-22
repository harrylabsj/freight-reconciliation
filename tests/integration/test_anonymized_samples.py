"""匿名样例回归：examples/anonymized/ 全链路实跑 == 实跑生成的金标（非手写）。

样例两种宿主形态（WorkBuddy 专家、Hermes 插件）共用；引擎行为变化时本测试
先红，确认是预期改动后才允许重新生成 expected-summary.json。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from conftest import HEADERS

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "examples" / "anonymized"
EXPECTED = json.loads((SAMPLE / "expected-summary.json").read_text())


def _wait_job(svc, job_id, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = svc.freight_get_job(job_id)
        if state["status"] in ("SUCCEEDED", "PARTIAL", "FAILED"):
            return state
        time.sleep(0.05)
    raise TimeoutError("job did not finish")


def test_anonymized_sample_end_to_end(svc):
    case = svc.freight_create_case("匿名样例", "CARRIER-A",
                                   "2026-09-01T00:00:00+08:00",
                                   "2026-10-01T00:00:00+08:00")
    cid = case["id"]
    for kind, header in HEADERS.items():
        doc = svc.freight_prepare_mapping(cid, kind, header)
        svc.admin_confirm(doc["confirmation_id"])
    for kind in ("trips", "bill", "rates"):
        svc.freight_register_asset(cid, str(SAMPLE / f"{kind}.csv"), kind)
    prep = svc.freight_prepare_rate_rules(cid)
    svc.admin_confirm(prep["confirmation_id"])
    job = svc.freight_start_run(cid)
    state = _wait_job(svc, job["job_id"])
    assert state["status"] == EXPECTED["job_status"]
    run_id = state["result"]["run_id"]

    got = svc.freight_get_summary(run_id)
    assert got["summary"] == EXPECTED["summary"]
    assert got["coverage"] == EXPECTED["coverage"]

    issues = svc.freight_list_issues(run_id, limit=100)["items"]
    assert sorted({i["code"] for i in issues}) == EXPECTED["issue_codes"]

    # 场景语义：AB02 多收 20000 分；AB03 无 trip_ref 只能待人工关联
    s = EXPECTED["summary"]
    assert s["positive_difference_minor"] == 20000
    assert s["unresolved_billed_minor"] == 50000
    # 三分区守恒
    assert s["source_signed_total_minor"] == (
        s["comparable_billed_minor"] + s["unresolved_billed_minor"]
        + s["out_of_scope_billed_minor"])
