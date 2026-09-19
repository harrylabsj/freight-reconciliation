"""补强覆盖：P3 候选与人工关联、历史查重、确认凭证重放（AT-016/022/048）。"""
from __future__ import annotations

import time

from conftest import HEADERS, write_csv


def _wait(svc, job_id):
    for _ in range(200):
        s = svc.freight_get_job(job_id)
        if s["status"] in ("SUCCEEDED", "PARTIAL", "FAILED"):
            return s
        time.sleep(0.05)
    raise TimeoutError()


def _setup(svc, tmp_path, extra_bills, history_rows=None):
    case = svc.freight_create_case("补强", "C-DEMO", "2026-09-01T00:00:00+08:00",
                                   "2026-10-01T00:00:00+08:00")
    cid = case["id"]
    for kind, header in HEADERS.items():
        doc = svc.freight_prepare_mapping(cid, kind, header)
        svc.admin_confirm(doc["confirmation_id"])
    doc = svc.freight_prepare_mapping(cid, "history_trips", HEADERS["trips"])
    svc.admin_confirm(doc["confirmation_id"])
    svc.freight_register_asset(cid, "03_examples/trips.csv", "trips")
    if history_rows:
        svc.freight_register_asset(
            cid, write_csv(tmp_path / "history.csv", HEADERS["trips"], history_rows),
            "history_trips")
    if extra_bills:
        svc.freight_register_asset(
            cid, write_csv(tmp_path / "bill.csv", HEADERS["bill"], extra_bills), "bill")
    rules = [{**{h: "" for h in HEADERS["rates"]}, **{
        "rule_id": "R1", "version": "1", "carrier_id": "C-DEMO", "route_id": "ROUTE-01",
        "vehicle_class": "CLASS-DEMO", "charge_code": "BASE", "currency": "CNY",
        "amount_basis": "GROSS", "effective_from": "2026-09-01T00:00:00+08:00",
        "effective_to": "2026-10-01T00:00:00+08:00", "formula": "PER_TRIP",
        "rate_minor": "100000", "source_refs": "t:1"}}]
    svc.freight_register_asset(
        cid, write_csv(tmp_path / "rates.csv", HEADERS["rates"], rules), "rates")
    prep = svc.freight_prepare_rate_rules(cid)
    svc.admin_confirm(prep["confirmation_id"])
    return cid


def test_p3_candidates_require_manual_confirm(svc, tmp_path):
    """无 trip_ref 的账单行：P3 仅产候选，人工确认后才绑定（§7.1）。"""
    bills = [{"line_id": "M1", "carrier_id": "C-DEMO", "trip_ref": "T999",
              "service_leg_id": "LEG-1", "charge_code": "BASE", "occurrence_id": "BASE",
              "amount_minor": "95000", "currency": "CNY", "amount_basis": "GROSS",
              "reversal_of": ""}]
    cid = _setup(svc, tmp_path, bills)
    job = svc.freight_start_run(cid)
    state = _wait(svc, job["job_id"])
    run1 = state["result"]["run_id"]
    issues = {i["code"] for i in svc.freight_list_issues(run1, limit=50)["items"]}
    assert "AMBIGUOUS" in issues  # 有 ref 但未命中 → 候选待人工，不猜选
    cand = svc.freight_list_match_candidates(cid)
    assert cand["items"] and cand["items"][0]["candidates"]  # 候选只是建议
    line_id = cand["items"][0]["bill_line_id"]
    trip_id = cand["items"][0]["candidates"][0]
    # prepare 后仍不生效，需管理页确认
    prep = svc.freight_prepare_match(cid, line_id, trip_id)
    m = svc.db.conn.execute(
        "SELECT state, method FROM match_assignments WHERE case_id=? AND bill_line_id=?",
        (cid, line_id)).fetchone()
    assert m["state"] in ("UNMATCHED", "AMBIGUOUS") and m["method"] in ("NONE", "P3")
    svc.admin_confirm(prep["confirmation_id"])
    m2 = svc.db.conn.execute(
        "SELECT state, method, trip_id FROM match_assignments WHERE case_id=?"
        " AND bill_line_id=?", (cid, line_id)).fetchone()
    assert m2["state"] == "EXACT" and m2["method"] == "MANUAL" and m2["trip_id"] == trip_id


def test_history_duplicate_candidate_with_coverage(svc, tmp_path):
    """提供历史台账 → 同车次标 HISTORICAL_DUPLICATE_CANDIDATE，且注明历史覆盖（§7.3）。"""
    history = [{"trip_id": "T001", "carrier_id": "C-DEMO", "route_id": "ROUTE-01",
                "vehicle_class": "CLASS-DEMO", "service_leg_id": "LEG-1",
                "departed_at": "2026-08-01T08:00:00+08:00",
                "execution_status": "EXECUTED", "order_ids": "OLD-1"}]
    bills = [{"line_id": "H1", "carrier_id": "C-DEMO", "trip_ref": "T001",
              "service_leg_id": "LEG-1", "charge_code": "BASE", "occurrence_id": "BASE",
              "amount_minor": "120000", "currency": "CNY", "amount_basis": "GROSS",
              "reversal_of": ""}]
    case = svc.freight_create_case("历史查重", "C-DEMO", "2026-09-01T00:00:00+08:00",
                                   "2026-10-01T00:00:00+08:00",
                                   history_coverage=("2026-08-01T00:00:00+08:00",
                                                     "2026-09-01T00:00:00+08:00"))
    cid = case["id"]
    for kind, header in HEADERS.items():
        doc = svc.freight_prepare_mapping(cid, kind, header)
        svc.admin_confirm(doc["confirmation_id"])
    doc = svc.freight_prepare_mapping(cid, "history_trips", HEADERS["trips"])
    svc.admin_confirm(doc["confirmation_id"])
    svc.freight_register_asset(cid, "03_examples/trips.csv", "trips")
    svc.freight_register_asset(cid, write_csv(tmp_path / "h.csv", HEADERS["trips"], history),
                               "history_trips")
    svc.freight_register_asset(cid, write_csv(tmp_path / "b.csv", HEADERS["bill"], bills),
                               "bill")
    rules = [{**{h: "" for h in HEADERS["rates"]}, **{
        "rule_id": "R1", "version": "1", "carrier_id": "C-DEMO", "route_id": "ROUTE-01",
        "vehicle_class": "CLASS-DEMO", "charge_code": "BASE", "currency": "CNY",
        "amount_basis": "GROSS", "effective_from": "2026-09-01T00:00:00+08:00",
        "effective_to": "2026-10-01T00:00:00+08:00", "formula": "PER_TRIP",
        "rate_minor": "100000", "source_refs": "t:1"}}]
    svc.freight_register_asset(cid, write_csv(tmp_path / "r.csv", HEADERS["rates"], rules),
                               "rates")
    prep = svc.freight_prepare_rate_rules(cid)
    svc.admin_confirm(prep["confirmation_id"])
    job = svc.freight_start_run(cid)
    state = _wait(svc, job["job_id"])
    run_id = state["result"]["run_id"]
    codes = {i["code"] for i in svc.freight_list_issues(run_id, limit=100)["items"]}
    assert "HISTORICAL_DUPLICATE_CANDIDATE" in codes
    note = svc.freight_get_summary(run_id)["history_coverage_note"]
    assert "历史台账覆盖" in note


def test_confirmation_replay_is_idempotent(golden_case):
    """同一确认请求重放：返回原结果，不产生第二个批准（AT-048）。"""
    gc = golden_case
    svc = gc["svc"]
    run_id, cid = gc["run_id"], gc["case_id"]
    row = svc.db.conn.execute(
        "SELECT group_id FROM results WHERE run_id=? LIMIT 1", (run_id,)).fetchone()
    prep = svc.freight_prepare_review(cid, run_id, row["group_id"],
                                      "NEEDS_EVIDENCE", "补签收后复核")
    first = svc.admin_confirm(prep["confirmation_id"])
    second = svc.admin_confirm(prep["confirmation_id"])
    assert second.get("idempotent") is True
    n = svc.db.conn.execute(
        "SELECT COUNT(*) FROM review_decisions WHERE run_id=? AND group_id=?",
        (run_id, row["group_id"])).fetchone()[0]
    assert n == 1
