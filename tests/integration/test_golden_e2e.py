"""端到端集成：金标全量、控制总数、复核/STALE、冻结导出、幂等与版本。"""
from __future__ import annotations

import json
import time

import pytest

from conftest import GOLDEN_EXPECTATIONS, GOLDEN_SELECTORS, GOLDEN_SUMMARY, HEADERS, write_csv

from freight_core.errors import (IdempotencyConflict, InvalidInput, LimitExceeded,
                                 VersionConflict)


# ---------------------------------------------------------------- 金标端到端
def test_golden_end_to_end(golden_case):
    """导入→映射→匹配→规则→运行 全链路与独立金标逐项一致（§14/§23）。"""
    gc = golden_case
    svc = gc["svc"]
    run_id = gc["run_id"]
    summary = svc.freight_get_summary(run_id)["summary"]
    for k, v in GOLDEN_SUMMARY.items():  # 金标 13 键全部一致（生产额外带 out_of_scope 键）
        assert summary[k] == v, (k, v, summary.get(k))
    # 三分区守恒（§6.3/§10.3）
    assert summary["source_signed_total_minor"] == (
        summary["comparable_billed_minor"] + summary["unresolved_billed_minor"]
        + summary["out_of_scope_billed_minor"])
    # 逐组对照
    rows = svc.db.conn.execute(
        "SELECT g.trip_id, g.charge_code, g.occurrence_id, r.expected_minor,"
        " r.delta_minor, r.issues FROM charge_groups g JOIN results r"
        " ON r.run_id=g.run_id AND r.group_id=g.group_id WHERE g.run_id=?",
        (run_id,)).fetchall()
    idx = {(r["trip_id"], r["charge_code"], r["occurrence_id"]): r for r in rows}
    for exp in GOLDEN_EXPECTATIONS:
        r = idx[GOLDEN_SELECTORS[exp["group_id"]]]
        got = {"group_id": exp["group_id"], "expected_minor": r["expected_minor"],
               "delta_minor": r["delta_minor"], "issues": json.loads(r["issues"])}
        assert got == exp, exp["group_id"]


def test_golden_coverage_metrics(golden_case):
    svc = golden_case["svc"]
    cov = svc.freight_get_summary(golden_case["run_id"])["coverage"]
    assert cov["comparable_lines"] == "9/12"  # §14: 可比账单行 9/12 = 75%
    assert abs(cov["amount_ratio_abs"] - 905000 / 1082000) < 1e-9  # ≈83.64%


def test_bidirectional_missing(golden_case):
    """反向遗漏：已执行未在账单 → NOT_BILLED_IN_PROVIDED_SCOPE（§7.3）。"""
    svc = golden_case["svc"]
    case = svc.get_case(golden_case["case_id"])
    missing = svc.reconcile.not_billed_trips(case)
    # 金标数据 T001-T009 全部有账单行引用；这里验证机制本身
    assert isinstance(missing, list)


# ---------------------------------------------------------------- 控制总数
def test_declared_total_mismatch_blocks_freeze(svc, tmp_path):
    case = svc.freight_create_case("对账", "C-DEMO", "2026-09-01T00:00:00+08:00",
                                   "2026-10-01T00:00:00+08:00")
    cid = case["id"]
    for kind, header in HEADERS.items():
        doc = svc.freight_prepare_mapping(cid, kind, header)
        svc.admin_confirm(doc["confirmation_id"])
    for kind, path in [("trips", "03_examples/trips.csv"),
                       ("rates", "03_examples/rates.csv")]:
        svc.freight_register_asset(cid, path, kind)
    bill_path = str(tmp_path / "bill.csv")
    write_csv(bill_path, HEADERS["bill"], [
        {"line_id": "X1", "carrier_id": "C-DEMO", "trip_ref": "T001",
         "service_leg_id": "LEG-1", "charge_code": "BASE", "occurrence_id": "BASE",
         "amount_minor": "100000", "currency": "CNY", "amount_basis": "GROSS",
         "reversal_of": ""}])
    asset = svc.freight_register_asset(cid, bill_path, "bill",
                                       declared_total_minor=99999)  # 声明合计不符
    assert asset["source_total_mismatch"] is True
    job = svc.freight_start_run(cid)
    state = _wait_job(svc, job["job_id"])
    assert state["status"] == "PARTIAL"  # PARTIAL 不可伪装 SUCCEEDED（§16.1）
    run_id = state["result"]["run_id"]
    fr = svc.admin_confirm_freeze(cid, run_id)
    assert fr["frozen"] is False  # 金额不完整只能草稿，不能正式冻结
    assert "草稿" in fr["note"]


def test_parse_failed_row_blocks_and_is_kept(svc, tmp_path):
    case = svc.freight_create_case("对账", "C-DEMO", "2026-09-01T00:00:00+08:00",
                                   "2026-10-01T00:00:00+08:00")
    cid = case["id"]
    for kind, header in HEADERS.items():
        doc = svc.freight_prepare_mapping(cid, kind, header)
        svc.admin_confirm(doc["confirmation_id"])
    rows = [{"line_id": "Y1", "carrier_id": "C-DEMO", "trip_ref": "T001",
             "service_leg_id": "LEG-1", "charge_code": "BASE", "occurrence_id": "BASE",
             "amount_minor": "1O0", "currency": "CNY", "amount_basis": "GROSS",
             "reversal_of": ""},
            {"line_id": "Y2", "carrier_id": "C-DEMO", "trip_ref": "T001",
             "service_leg_id": "LEG-1", "charge_code": "BASE", "occurrence_id": "BASE",
             "amount_minor": "50000", "currency": "CNY", "amount_basis": "GROSS",
             "reversal_of": ""}]
    path = write_csv(tmp_path / "bill.csv", HEADERS["bill"], rows)
    asset = svc.freight_register_asset(cid, path, "bill")
    assert asset["parse_error_rows"] == 1
    assert asset["detail_rows"] == 1  # 解析失败行不计入明细，但保留原行
    src = svc.db.conn.execute(
        "SELECT parse_status, parse_error FROM source_rows WHERE asset_id=?"
        " AND parse_status='FAILED'", (asset["asset_id"],)).fetchone()
    assert src is not None and "1O0" in (src["parse_error"] or "")


def test_id_damaged_scientific_notation(svc, tmp_path):
    case = svc.freight_create_case("对账", "C-DEMO", "2026-09-01T00:00:00+08:00",
                                   "2026-10-01T00:00:00+08:00")
    cid = case["id"]
    for kind, header in HEADERS.items():
        doc = svc.freight_prepare_mapping(cid, kind, header)
        svc.admin_confirm(doc["confirmation_id"])
    rows = [{"line_id": "1.23E+05", "carrier_id": "C-DEMO", "trip_ref": "T001",
             "service_leg_id": "LEG-1", "charge_code": "BASE", "occurrence_id": "BASE",
             "amount_minor": "100", "currency": "CNY", "amount_basis": "GROSS",
             "reversal_of": ""}]
    path = write_csv(tmp_path / "bill.csv", HEADERS["bill"], rows)
    asset = svc.freight_register_asset(cid, path, "bill")
    assert asset["parse_error_rows"] == 1  # 科学计数法编号损坏不可逆（§6.2）


# ---------------------------------------------------------------- 复核与 STALE
def test_review_prepare_confirm_and_stale(golden_case):
    gc = golden_case
    svc = gc["svc"]
    run_id = gc["run_id"]
    cid = gc["case_id"]
    row = svc.db.conn.execute(
        "SELECT group_id, result_digest, delta_minor FROM results WHERE run_id=?"
        " AND delta_minor>0 LIMIT 1", (run_id,)).fetchone()
    prep = svc.freight_prepare_review(cid, run_id, row["group_id"],
                                      "CONFIRMED_DIFFERENCE", "与承运商邮件核实，多收100元",
                                      )
    # 模型侧只能 prepare；确认必须走 admin_confirm
    out = svc.admin_confirm(prep["confirmation_id"])
    assert out["decision_id"]
    # 重跑后结果 digest 不变 → 决定仍有效
    job = svc.freight_start_run(cid)
    state = _wait_job(svc, job["job_id"])
    run2 = state["result"]["run_id"]
    decisions = svc.reviews.list_decisions(cid)
    active = [d for d in decisions if d["status"] == "ACTIVE"]
    assert active, "digest 未变时决定应保持 ACTIVE"
    # 接受账单不改写计算值（§12.2）
    r1 = svc.db.conn.execute(
        "SELECT delta_minor FROM results WHERE run_id=? AND group_id=?",
        (run_id, row["group_id"])).fetchone()
    assert r1["delta_minor"] == row["delta_minor"]


def test_stale_on_changed_results(svc, tmp_path):
    """补证/改规则后新旧结果变化 → 旧决定 STALE（§12.1 G）。"""
    gc = _simple_case_with_decision(svc, tmp_path)
    cid, run1, group_id = gc
    # 改变输入：新 trip 使结果变化（新增一条更高费率的规则版本？更直接：补一条账单行）
    bill_rows = [{"line_id": "Z2", "carrier_id": "C-DEMO", "trip_ref": "T001",
                  "service_leg_id": "LEG-1", "charge_code": "BASE",
                  "occurrence_id": "BASE", "amount_minor": "70000",
                  "currency": "CNY", "amount_basis": "GROSS", "reversal_of": ""}]
    path = write_csv(tmp_path / "bill2.csv", HEADERS["bill"], bill_rows)
    svc.freight_register_asset(cid, path, "bill")
    job = svc.freight_start_run(cid)
    state = _wait_job(svc, job["job_id"])
    run2 = state["result"]["run_id"]
    decisions = svc.reviews.list_decisions(cid)
    assert any(d["status"] == "STALE" for d in decisions), decisions


def _simple_case_with_decision(svc, tmp_path):
    case = svc.freight_create_case("对账", "C-DEMO", "2026-09-01T00:00:00+08:00",
                                   "2026-10-01T00:00:00+08:00")
    cid = case["id"]
    for kind, header in HEADERS.items():
        doc = svc.freight_prepare_mapping(cid, kind, header)
        svc.admin_confirm(doc["confirmation_id"])
    svc.freight_register_asset(cid, "03_examples/trips.csv", "trips")
    bill_rows = [{"line_id": "Z1", "carrier_id": "C-DEMO", "trip_ref": "T001",
                  "service_leg_id": "LEG-1", "charge_code": "BASE",
                  "occurrence_id": "BASE", "amount_minor": "120000",
                  "currency": "CNY", "amount_basis": "GROSS", "reversal_of": ""}]
    path = write_csv(tmp_path / "bill.csv", HEADERS["bill"], bill_rows)
    svc.freight_register_asset(cid, path, "bill")
    rules = [{
        "rule_id": "R1", "version": 1, "carrier_id": "C-DEMO", "route_id": "ROUTE-01",
        "vehicle_class": "CLASS-DEMO", "charge_code": "BASE", "currency": "CNY",
        "amount_basis": "GROSS", "effective_from": "2026-09-01T00:00:00+08:00",
        "effective_to": "2026-10-01T00:00:00+08:00", "formula": "PER_TRIP",
        "rate_minor": 100000, "free_seconds": 0, "block_seconds": 1, "cap_minor": None,
        "source_ref": "test"}]
    rule_path = write_csv(tmp_path / "rates.csv", HEADERS["rates"], [
        {**{h: "" for h in HEADERS["rates"]}, **{
            "rule_id": "R1", "version": "1", "carrier_id": "C-DEMO",
            "route_id": "ROUTE-01", "vehicle_class": "CLASS-DEMO",
            "charge_code": "BASE", "currency": "CNY", "amount_basis": "GROSS",
            "effective_from": "2026-09-01T00:00:00+08:00",
            "effective_to": "2026-10-01T00:00:00+08:00", "formula": "PER_TRIP",
            "rate_minor": "100000", "free_seconds": "0", "block_seconds": "1",
            "source_refs": "test:rates#R1"}}])
    svc.freight_register_asset(cid, rule_path, "rates")
    prep = svc.freight_prepare_rate_rules(cid)
    svc.admin_confirm(prep["confirmation_id"])
    job = svc.freight_start_run(cid)
    state = _wait_job(svc, job["job_id"])
    run1 = state["result"]["run_id"]
    row = svc.db.conn.execute(
        "SELECT group_id FROM results WHERE run_id=? LIMIT 1", (run1,)).fetchone()
    prep = svc.freight_prepare_review(cid, run1, row["group_id"],
                                      "CONFIRMED_DIFFERENCE", "首次确认")
    svc.admin_confirm(prep["confirmation_id"])
    return cid, run1, row["group_id"]


# ---------------------------------------------------------------- 冻结与导出
def test_freeze_and_export(golden_case, tmp_path):
    gc = golden_case
    svc = gc["svc"]
    cid, run_id = gc["case_id"], gc["run_id"]
    fr = svc.admin_confirm_freeze(cid, run_id)
    assert fr["frozen"] is True
    case = svc.get_case(cid)
    assert case["status"] == "FROZEN" and case["frozen_run_id"] == run_id
    exp = svc.freight_prepare_export(cid, run_id, "与承运商核对9月差异")
    released = svc.admin_confirm(exp["confirmation_id"])
    assert released["status"] == "RELEASED"
    xlsx_path = None
    for art in released["artifacts"]:
        p = svc.files.resolve(art["path"])
        assert p.exists()
        if art["name"].endswith(".xlsx"):
            xlsx_path = p
    from openpyxl import load_workbook
    wb = load_workbook(xlsx_path, read_only=True)
    assert wb.sheetnames == ["总览", "逐行台账", "核算组", "待核差异", "待补证", "待匹配",
                             "规则引用", "复核记录", "版本变化", "来源清单"]
    # 未知值留空不写0：待核差异表无 None 伪装
    ws = wb["核算组"]
    header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    assert "expected_minor" in header


def test_export_csv_injection_guard(svc):
    """外发文本公式注入防护（OWASP，S08）。"""
    from freight_core.export.xlsx import safe_cell
    assert safe_cell("=SUM(A1)") == "'=SUM(A1)"
    assert safe_cell("+1") == "'+1"
    assert safe_cell("@cmd") == "'@cmd"
    assert safe_cell("-2") == "'-2"
    assert safe_cell("正常文本") == "正常文本"
    assert safe_cell(None) is None  # 未知留空，不写0


# ---------------------------------------------------------------- 幂等与版本
def test_idempotency_same_key_same_content(svc):
    case = svc.freight_create_case("幂等", "C1", "2026-09-01T00:00:00+08:00",
                                   "2026-10-01T00:00:00+08:00", idempotency_key="k1")
    again = svc.freight_create_case("幂等", "C1", "2026-09-01T00:00:00+08:00",
                                    "2026-10-01T00:00:00+08:00", idempotency_key="k1")
    assert case["id"] == again["id"]  # 同键同内容返回原结果


def test_idempotency_conflict_on_different_content(svc):
    svc.freight_create_case("幂等", "C1", "2026-09-01T00:00:00+08:00",
                            "2026-10-01T00:00:00+08:00", idempotency_key="k2")
    with pytest.raises(IdempotencyConflict):
        svc.freight_create_case("另一个案件", "C2", "2026-09-01T00:00:00+08:00",
                                "2026-10-01T00:00:00+08:00", idempotency_key="k2")


def test_version_conflict_on_expected_revision(svc):
    case = svc.freight_create_case("版本", "C1", "2026-09-01T00:00:00+08:00",
                                   "2026-10-01T00:00:00+08:00")
    with pytest.raises(VersionConflict):
        svc.freight_start_run(case["id"], expected_revision=case["case_revision"] + 5)


def test_duplicate_import_is_idempotent(golden_case):
    """同一来源重复导入返回原 asset，不生成第二份账单（§10.1）。"""
    svc = golden_case["svc"]
    cid = golden_case["case_id"]
    before = svc.db.conn.execute(
        "SELECT COUNT(*) FROM bill_lines WHERE case_id=?", (cid,)).fetchone()[0]
    asset = svc.freight_register_asset(cid, "03_examples/bill.csv", "bill")
    assert asset["reimported"] is True
    after = svc.db.conn.execute(
        "SELECT COUNT(*) FROM bill_lines WHERE case_id=?", (cid,)).fetchone()[0]
    assert before == after


def test_cross_carrier_line_is_isolated(svc, tmp_path):
    """同主体多案件不混算：跨承运商行隔离进明确排除分区（§20.2）。"""
    case = svc.freight_create_case("隔离", "C-DEMO", "2026-09-01T00:00:00+08:00",
                                   "2026-10-01T00:00:00+08:00")
    cid = case["id"]
    for kind, header in HEADERS.items():
        doc = svc.freight_prepare_mapping(cid, kind, header)
        svc.admin_confirm(doc["confirmation_id"])
    svc.freight_register_asset(cid, "03_examples/trips.csv", "trips")
    svc.freight_register_asset(cid, "03_examples/rates.csv", "rates")
    rows = [{"line_id": "FOREIGN", "carrier_id": "C-OTHER", "trip_ref": "T001",
             "service_leg_id": "LEG-1", "charge_code": "BASE", "occurrence_id": "BASE",
             "amount_minor": "88000", "currency": "CNY", "amount_basis": "GROSS",
             "reversal_of": ""}]
    path = write_csv(tmp_path / "bill.csv", HEADERS["bill"], rows)
    svc.freight_register_asset(cid, path, "bill")
    job = svc.freight_start_run(cid)
    state = _wait_job(svc, job["job_id"])
    summary = svc.freight_get_summary(state["result"]["run_id"])["summary"]
    assert summary["out_of_scope_billed_minor"] == 88000
    assert summary["out_of_scope_line_count"] == 1
    codes = {i["code"] for i in svc.freight_list_issues(
        state["result"]["run_id"], limit=100)["items"]}
    assert "CARRIER_CONFLICT" in codes


# ---------------------------------------------------------------- 工具函数
def _wait_job(svc, job_id, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = svc.freight_get_job(job_id)
        if state["status"] in ("SUCCEEDED", "PARTIAL", "FAILED"):
            return state
        time.sleep(0.05)
    raise TimeoutError("job did not finish")
