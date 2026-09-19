"""共享测试夹具：合成数据、服务实例与金标案件构建。"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from freight_core.service import ReconciliationService  # noqa: E402

GOLDEN_SUMMARY = json.loads((ROOT / "03_examples/golden-summary.json").read_text())
GOLDEN_EXPECTATIONS = json.loads(
    (ROOT / "03_examples/golden-expectations.json").read_text())

HEADERS = {
    "trips": ["trip_id", "carrier_id", "route_id", "vehicle_class", "service_leg_id",
              "departed_at", "execution_status", "order_ids"],
    "bill": ["line_id", "carrier_id", "trip_ref", "service_leg_id", "charge_code",
             "occurrence_id", "amount_minor", "currency", "amount_basis", "reversal_of"],
    "rates": ["schema_version", "rule_id", "version", "workspace_id", "carrier_id",
              "route_id", "vehicle_class", "charge_code", "currency", "amount_basis",
              "effective_from", "effective_to", "formula", "rate_minor", "free_seconds",
              "block_seconds", "cap_minor", "confirmed", "confirmation_ref", "source_refs"],
    "waiting": ["event_id", "trip_id", "occurrence_id", "arrived_at", "departed_at",
                "evidence_ref", "verified_status"],
    "pod": ["evidence_id", "trip_id", "occurrence_id", "evidence_type", "asset_filename",
            "page_or_row", "verified_status", "reviewer_ref"],
    "receipts": ["receipt_id", "trip_id", "occurrence_id", "amount_minor", "currency",
                 "amount_basis", "evidence_ref", "verified_status"],
}

# 金标组 → (trip_id, charge_code, occurrence_id)
GOLDEN_SELECTORS = {
    "G01": ("T001", "BASE", "BASE"), "G02": ("T002", "BASE", "BASE"),
    "G03": ("T003", "WAIT", "EVENT-1"), "G04": ("T004", "BASE", "BASE"),
    "G05": ("T005", "TOLL", "EVENT-1"), "G06": ("T006", "BASE", "BASE"),
    "G07": ("T007", "BASE", "BASE"), "G08": ("T008", "BASE", "BASE"),
    "G09": ("T009", "BASE", "BASE"), "G10": (None, "BASE", "BASE"),
}


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> str:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return str(path)


@pytest.fixture()
def svc(tmp_path):
    service = ReconciliationService(str(tmp_path / "ws"), workspace_id="WS-DEMO",
                                    actor_id="tester")
    yield service
    service.close()


@pytest.fixture()
def golden_case(svc, tmp_path):
    """完整金标案件：映射→导入→POD→规则→运行。返回 (case_id, run_id)。"""
    case = svc.freight_create_case("9月对账", "C-DEMO", "2026-09-01T00:00:00+08:00",
                                   "2026-10-01T00:00:00+08:00")
    cid = case["id"]
    for kind, header in HEADERS.items():
        doc = svc.freight_prepare_mapping(cid, kind, header)
        svc.admin_confirm(doc["confirmation_id"])
    for kind, path in [("trips", ROOT / "03_examples/trips.csv"),
                       ("bill", ROOT / "03_examples/bill.csv"),
                       ("rates", ROOT / "03_examples/rates.csv")]:
        svc.freight_register_asset(cid, str(path), kind)
    wait_rows = [{"event_id": "E03", "trip_id": "T003", "occurrence_id": "EVENT-1",
                  "arrived_at": "2026-09-03T08:00:00+08:00",
                  "departed_at": "2026-09-03T11:00:00+08:00",
                  "evidence_ref": "gate-log-3", "verified_status": "VERIFIED"}]
    wait_path = write_csv(tmp_path / "waiting.csv", HEADERS["waiting"], wait_rows)
    svc.freight_register_asset(cid, wait_path, "waiting")
    pod_rows = [{"evidence_id": f"P{i:02d}", "trip_id": f"T{i:03d}", "occurrence_id": "",
                 "evidence_type": "POD", "asset_filename": f"pod-T{i:03d}.pdf",
                 "page_or_row": "1",
                 "verified_status": "MISSING" if i == 8 else "VERIFIED",
                 "reviewer_ref": "rev-01"} for i in range(1, 10)]
    pod_path = write_csv(tmp_path / "pod.csv", HEADERS["pod"], pod_rows)
    svc.freight_register_asset(cid, pod_path, "pod")
    prep = svc.freight_prepare_rate_rules(cid)
    svc.admin_confirm(prep["confirmation_id"])
    job = svc.freight_start_run(cid)
    for _ in range(200):
        state = svc.freight_get_job(job["job_id"])
        if state["status"] in ("SUCCEEDED", "PARTIAL", "FAILED"):
            break
        time.sleep(0.05)
    assert state["status"] in ("SUCCEEDED", "PARTIAL"), state
    return {"case_id": cid, "run_id": state["result"]["run_id"], "svc": svc,
            "tmp_path": tmp_path}
