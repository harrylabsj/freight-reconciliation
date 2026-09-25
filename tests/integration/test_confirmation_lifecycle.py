"""确认路由的生命周期回归：确认过的请求不得留在管理页「待确认」列表里。

背景（2026-09-25 实测发现的既有缺陷）：`ReconciliationService.admin_confirm` 里只有部分
kind 分支把 confirmation_requests.status 置成 CONFIRMED，mapping 分支漏写——映射确认后
管理页待确认列表会一直挂着那条已确认的幽灵条目（重复确认虽幂等，但看着像没生效）。
修复后由 admin_confirm 统一做一次幂等兜底；本文件钉住该行为，含「失败不得标记成功」。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

from conftest import HEADERS  # noqa: E402
from freight_core.errors import InvalidInput  # noqa: E402
from freight_core.service import ReconciliationService  # noqa: E402

PENDING_SQL = "SELECT * FROM confirmation_requests WHERE status='PENDING'"


def _status(svc: ReconciliationService, confirmation_id: str) -> str:
    row = svc.db.conn.execute(
        "SELECT status FROM confirmation_requests WHERE id=?",
        (confirmation_id,)).fetchone()
    return row["status"]


def _pending_ids(svc: ReconciliationService) -> set[str]:
    return {r["id"] for r in svc.db.conn.execute(PENDING_SQL).fetchall()}


def _case(svc: ReconciliationService) -> dict:
    return svc.freight_create_case("确认生命周期", "C-CONF", "2026-09-01T00:00:00+08:00",
                                   "2026-10-01T00:00:00+08:00")


def test_mapping_confirm_leaves_no_ghost_pending(tmp_path):
    """映射确认（曾经的缺陷点）：请求落 CONFIRMED，待确认列表清空。"""
    svc = ReconciliationService(str(tmp_path / "ws"), workspace_id="WS-CONF")
    try:
        case = _case(svc)
        prep = svc.freight_prepare_mapping(case["id"], "bill", HEADERS["bill"])
        assert _status(svc, prep["confirmation_id"]) == "PENDING"
        svc.admin_confirm(prep["confirmation_id"])
        assert _status(svc, prep["confirmation_id"]) == "CONFIRMED"
        assert _pending_ids(svc) == set()
    finally:
        svc.close()


def test_confirmed_kind_marks_request_and_other_kinds_keep_pending(tmp_path):
    """同一案件两条待确认：确认一条只清一条，另一条仍在列表里。"""
    svc = ReconciliationService(str(tmp_path / "ws"), workspace_id="WS-CONF")
    try:
        case = _case(svc)
        bill = svc.freight_prepare_mapping(case["id"], "bill", HEADERS["bill"])
        trips = svc.freight_prepare_mapping(case["id"], "trips", HEADERS["trips"])
        assert _pending_ids(svc) == {bill["confirmation_id"], trips["confirmation_id"]}
        svc.admin_confirm(bill["confirmation_id"])
        assert _status(svc, bill["confirmation_id"]) == "CONFIRMED"
        assert _pending_ids(svc) == {trips["confirmation_id"]}
    finally:
        svc.close()


def test_repeated_confirm_is_idempotent(tmp_path):
    """重复确认返回原结果、不产生第二个批准，且不改变已确认状态。"""
    svc = ReconciliationService(str(tmp_path / "ws"), workspace_id="WS-CONF")
    try:
        case = _case(svc)
        prep = svc.freight_prepare_mapping(case["id"], "bill", HEADERS["bill"])
        svc.admin_confirm(prep["confirmation_id"])
        again = svc.admin_confirm(prep["confirmation_id"])
        assert again.get("idempotent") is True
        assert _status(svc, prep["confirmation_id"]) == "CONFIRMED"
        rows = svc.db.conn.execute(
            "SELECT COUNT(*) FROM confirmation_requests WHERE id=?",
            (prep["confirmation_id"],)).fetchone()[0]
        assert rows == 1
    finally:
        svc.close()


def test_failed_confirm_does_not_mark_request_confirmed(tmp_path):
    """确认失败（未知 kind）必须保持 PENDING——不能把失败当成功落库。"""
    svc = ReconciliationService(str(tmp_path / "ws"), workspace_id="WS-CONF")
    try:
        case = _case(svc)
        bogus = "CREQ-BOGUS-KIND"
        with svc.db.conn:
            svc.db.conn.execute(
                "INSERT INTO confirmation_requests (id, kind, workspace_id, case_id,"
                " object_digest, payload, status, nonce, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (bogus, "no_such_kind", "WS-CONF", case["id"], "digest-0", "{}",
                 "PENDING", "nonce-0", "2026-09-25T00:00:00+00:00"))
        with pytest.raises(InvalidInput):
            svc.admin_confirm(bogus)
        assert _status(svc, bogus) == "PENDING"
    finally:
        svc.close()
