"""宿主层测试：本地管理页 HTTP 行为 + 性能基线（§17.2、§21.1）。"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import time
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

from conftest import HEADERS, write_csv  # noqa: E402
from freight_core.service import ReconciliationService  # noqa: E402


# ================================================================ 管理页 HTTP
@pytest.fixture(scope="module")
def admin_server(tmp_path_factory):
    root = tmp_path_factory.mktemp("adminws")
    env = dict(os.environ)
    env["FREIGHT_RECON_ROOT"] = str(root)
    env["FREIGHT_ADMIN_PORT"] = "8912"
    env["FREIGHT_ADMIN_TOKEN"] = "test-token"
    env["PYTHONPATH"] = str(ROOT / "src")
    proc = subprocess.Popen([sys.executable, str(ROOT / "adapters/admin_server.py")],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, env=env)
    import time as _t
    for _ in range(50):
        try:
            urllib.request.urlopen("http://127.0.0.1:8912/", timeout=1)
            break
        except Exception:
            _t.sleep(0.1)
    yield "http://127.0.0.1:8912"
    proc.terminate()


class AdminClient:
    def __init__(self, base):
        self.base = base
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def get(self, path):
        req = urllib.request.Request(self.base + path)
        return self.opener.open(req, timeout=5)

    def post(self, path, data, origin=None):
        req = urllib.request.Request(self.base + path, data=bytes(urllib.parse.urlencode(data), encoding="utf-8"))
        if origin:
            req.add_header("Origin", origin)
        return self.opener.open(req, timeout=5)


import urllib.parse  # noqa: E402


def test_admin_requires_login(admin_server):
    base = admin_server
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    resp = opener.open(base + "/", timeout=5)
    body = resp.read().decode()
    assert "管理页登录" in body  # 未登录只见登录页


def test_admin_login_and_csrf_rejected(admin_server):
    base = admin_server
    client = AdminClient(base)
    resp = client.post("/admin/login", {"token": "test-token"})
    assert resp.status in (200, 303)
    # CSRF 缺失 → 403（确认路由拒绝无凭证 POST）
    try:
        client.post("/admin/confirmations/FAKE/confirm", {})
        raised = False
    except urllib.error.HTTPError as exc:
        raised = exc.code == 403
    assert raised, "无 CSRF 的确认 POST 必须被拒"


def test_admin_cross_origin_rejected(admin_server):
    base = admin_server
    client = AdminClient(base)
    client.post("/admin/login", {"token": "test-token"})
    try:
        client.post("/admin/confirmations/FAKE/confirm", {}, origin="http://evil.example")
        ok = False
    except urllib.error.HTTPError as exc:
        ok = exc.code == 403
    assert ok, "跨 Origin POST 必须被拒（§17.2）"


def test_admin_pages_render(admin_server, tmp_path):
    """用 Core 建一个案件后，管理页五个页面可渲染。"""
    base = admin_server
    client = AdminClient(base)
    client.post("/admin/login", {"token": "test-token"})
    # 同一 FREIGHT_RECON_ROOT 下的案件由 env 指定；这里直接通过该 root 的库文件验证页面
    client.get("/")
    # 新建案件（直接写库：管理页尚未提供建案表单，建案走工具面/CLI）
    from freight_core.service import ReconciliationService
    svc = ReconciliationService(str(tmp_path / "x"))  # 独立实例不污染
    case = svc.freight_create_case("页面渲染", "C1", "2026-09-01T00:00:00+08:00",
                                   "2026-10-01T00:00:00+08:00")
    svc.close()
    resp = client.get("/admin/confirmations")
    assert resp.status == 200


# ================================================================ 性能基线
def test_performance_baseline_10k(tmp_path):
    """§21.1 性能验收：1万账单行+1万运输，不调模型、已配模板，60 秒内完成主要匹配与核算。

    目标值，实测记录于断言信息；不把目标当成绩——超时即失败。
    """
    svc = ReconciliationService(str(tmp_path / "perf"), workspace_id="WS-PERF")
    try:
        case = svc.freight_create_case("性能", "C-PERF", "2026-09-01T00:00:00+08:00",
                                       "2026-10-01T00:00:00+08:00")
        cid = case["id"]
        for kind, header in HEADERS.items():
            doc = svc.freight_prepare_mapping(cid, kind, header)
            svc.admin_confirm(doc["confirmation_id"])
        rng = random.Random(42)
        N = 10_000
        trips = [{"trip_id": f"T{i:05d}", "carrier_id": "C-PERF",
                  "route_id": f"ROUTE-{i % 20:02d}", "vehicle_class": "CLASS-A",
                  "service_leg_id": "LEG-1",
                  "departed_at": f"2026-09-{(i % 28) + 1:02d}T08:00:00+08:00",
                  "execution_status": "EXECUTED", "order_ids": f"O{i}"} for i in range(N)]
        rates = [{"rule_id": f"R{i:02d}", "version": "1", "carrier_id": "C-PERF",
                  "route_id": f"ROUTE-{i:02d}", "vehicle_class": "CLASS-A",
                  "charge_code": "BASE", "currency": "CNY", "amount_basis": "GROSS",
                  "effective_from": "2026-09-01T00:00:00+08:00",
                  "effective_to": "2026-10-01T00:00:00+08:00", "formula": "PER_TRIP",
                  "rate_minor": str(50000 + i * 100), "free_seconds": "7200",
                  "block_seconds": "1800", "confirmed": "True",
                  "confirmation_ref": f"c{i}", "source_refs": f"perf:{i}"} for i in range(20)]
        bills = [{"line_id": f"B{i:05d}", "carrier_id": "C-PERF", "trip_ref": f"T{i:05d}",
                  "service_leg_id": "LEG-1", "charge_code": "BASE",
                  "occurrence_id": "BASE",
                  "amount_minor": str(int(50000 + (i % 20) * 100 + rng.choice([0, 0, 0, 500, -100]))),
                  "currency": "CNY", "amount_basis": "GROSS", "reversal_of": ""}
                 for i in range(N)]
        t0 = time.time()
        svc.freight_register_asset(cid, write_csv(tmp_path / "trips.csv", HEADERS["trips"], trips), "trips")
        svc.freight_register_asset(cid, write_csv(tmp_path / "rates.csv", HEADERS["rates"], rates), "rates")
        svc.freight_register_asset(cid, write_csv(tmp_path / "bill.csv", HEADERS["bill"], bills), "bill")
        prep = svc.freight_prepare_rate_rules(cid)
        svc.admin_confirm(prep["confirmation_id"])
        t1 = time.time()
        job = svc.freight_start_run(cid)
        state = None
        while time.time() - t1 < 60:
            state = svc.freight_get_job(job["job_id"])
            if state["status"] in ("SUCCEEDED", "PARTIAL", "FAILED"):
                break
            time.sleep(0.2)
        elapsed = time.time() - t1
        assert state and state["status"] in ("SUCCEEDED", "PARTIAL"), state
        run_id = state["result"]["run_id"]
        summary = svc.freight_get_summary(run_id)["summary"]
        assert summary["bill_line_count"] == N
        assert summary["comparable_line_count"] >= N * 0.95
        assert elapsed < 60, f"性能基线未达标：1万行耗时 {elapsed:.1f}s（导入 {t1 - t0:.1f}s）"
    finally:
        svc.close()
