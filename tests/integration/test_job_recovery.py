"""失败恢复：连接器进程崩溃后，残留 job 必须可识别、可恢复、可确定性重跑。

模拟方式：直接在库里放一个 RUNNING job（无对应线程，等价于进程已死），
关闭服务后用同一案件库重开 —— 新实例启动清扫应把它标记 FAILED/
RUN_INTERRUPTED 并给出 recovery_action，案件回到 READY 可立即重跑。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from conftest import HEADERS

from freight_core.service import ReconciliationService, _new_id, _now

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "examples" / "anonymized"


def _build_case(svc):
    case = svc.freight_create_case("恢复演练", "CARRIER-A",
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
    return cid


def _wait_job(svc, job_id, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = svc.freight_get_job(job_id)
        if state["status"] in ("SUCCEEDED", "PARTIAL", "FAILED"):
            return state
        time.sleep(0.05)
    raise TimeoutError("job did not finish")


def _summary_of(svc, cid):
    job = svc.freight_start_run(cid)
    state = _wait_job(svc, job["job_id"])
    assert state["status"] == "SUCCEEDED"
    return svc.freight_get_summary(state["result"]["run_id"])["summary"]


def test_interrupted_job_is_marked_and_rerun_is_deterministic(tmp_path):
    root = str(tmp_path / "ws")
    svc = ReconciliationService(root, workspace_id="WS-DEMO", actor_id="tester")
    cid = _build_case(svc)
    baseline = _summary_of(svc, cid)  # 先跑一版干净基线

    # 模拟崩溃：手工落一个 RUNNING job（无线程），案件卡在 RUNNING
    ghost = _new_id("JOB")
    with svc.db.conn:
        svc.db.conn.execute(
            "INSERT INTO jobs (id, case_id, workspace_id, operation, status,"
            " idempotency_key, request_digest, payload, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (ghost, cid, "WS-DEMO", "start_run", "RUNNING", None, "ghost",
             json.dumps({"supersedes_run_id": None}), _now()))
        svc.db.conn.execute("UPDATE cases SET status='RUNNING' WHERE id=?", (cid,))
    svc.close()

    # 同一案件库重开（= 连接器进程重启）
    svc2 = ReconciliationService(root, workspace_id="WS-DEMO", actor_id="tester")
    state = svc2.freight_get_job(ghost)
    assert state["status"] == "FAILED"
    assert state["error"]["code"] == "RUN_INTERRUPTED"
    assert state["error"]["retryable"] is True
    assert "freight_start_run" in state["error"]["recovery_action"]
    assert svc2.get_case(cid)["status"] == "READY"  # 不再卡 RUNNING

    # 重跑确定性：输入摘要冻结，摘要与崩溃前基线逐项一致
    assert _summary_of(svc2, cid) == baseline
    svc2.close()


def test_clean_restart_does_not_touch_terminal_jobs(tmp_path):
    """正常结束的 job 不受启动清扫影响（只清 QUEUED/RUNNING 残留）。"""
    root = str(tmp_path / "ws")
    svc = ReconciliationService(root, workspace_id="WS-DEMO", actor_id="tester")
    cid = _build_case(svc)
    job = svc.freight_start_run(cid)
    done = _wait_job(svc, job["job_id"])
    svc.close()

    svc2 = ReconciliationService(root, workspace_id="WS-DEMO", actor_id="tester")
    again = svc2.freight_get_job(job["job_id"])
    assert again["status"] == done["status"]
    assert again["error"] is None
    svc2.close()
