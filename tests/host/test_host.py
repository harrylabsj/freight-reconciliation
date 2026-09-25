"""宿主层测试：本地管理页 HTTP 行为 + 性能基线（§17.2、§21.1）。"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

from conftest import HEADERS, write_csv  # noqa: E402
from freight_core.service import ReconciliationService  # noqa: E402

ADMIN_PORT = "8912"
ADMIN_TOKEN = "test-token"


# ================================================================ 管理页 HTTP
@pytest.fixture(scope="module")
def admin_env(tmp_path_factory):
    """独立管理页进程 + 私有案件根目录（模块级复用）。"""
    root = tmp_path_factory.mktemp("adminws")
    env = dict(os.environ)
    env["FREIGHT_RECON_ROOT"] = str(root)
    env["FREIGHT_ADMIN_PORT"] = ADMIN_PORT
    env["FREIGHT_ADMIN_TOKEN"] = ADMIN_TOKEN
    env["PYTHONPATH"] = str(ROOT / "src")
    env.pop("FREIGHT_LANG", None)
    # 进程 locale 固定英文：目录要求界面英文默认，中文只能由 Accept-Language 触发。
    env["LANG"] = env["LC_ALL"] = "en_US.UTF-8"
    proc = subprocess.Popen([sys.executable, str(ROOT / "adapters/admin_server.py")],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, env=env)
    base = f"http://127.0.0.1:{ADMIN_PORT}"
    for _ in range(50):
        try:
            urllib.request.urlopen(base + "/", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    yield {"base": base, "root": root, "token": ADMIN_TOKEN}
    proc.terminate()
    proc.wait(timeout=10)


class AdminClient:
    def __init__(self, base, accept_language=None, token=ADMIN_TOKEN):
        self.base = base
        self.accept_language = accept_language
        self.token = token
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def _open(self, req):
        if self.accept_language:
            req.add_header("Accept-Language", self.accept_language)
        return self.opener.open(req, timeout=5)

    def get(self, path):
        return self._open(urllib.request.Request(self.base + path))

    def text(self, path) -> str:
        return self.get(path).read().decode()

    def post(self, path, data=None, origin=None):
        body = bytes(urllib.parse.urlencode(data or {}), encoding="utf-8")
        req = urllib.request.Request(self.base + path, data=body)
        if origin:
            req.add_header("Origin", origin)
        return self._open(req)

    def login(self):
        return self.post("/admin/login", {"token": self.token})

    def csrf(self) -> str:
        match = re.search(r'name=csrf value="([^"]*)"', self.text("/admin/confirmations"))
        return match.group(1) if match else ""


def test_admin_requires_login_english_default(admin_env):
    """未登录只见登录页；默认语言英文（locale 英文、无 Accept-Language）。"""
    body = AdminClient(admin_env["base"]).text("/")
    assert 'lang="en"' in body
    assert "Admin sign-in" in body
    assert "管理页登录" not in body


def test_admin_ui_follows_accept_language(admin_env):
    """Accept-Language: zh-CN → 中文界面（英文文案不再出现）。"""
    client = AdminClient(admin_env["base"], accept_language="zh-CN,zh;q=0.9,en;q=0.8")
    body = client.text("/")
    assert 'lang="zh"' in body
    assert "管理页登录" in body
    assert "Admin sign-in" not in body


def test_admin_login_and_csrf_rejected(admin_env):
    client = AdminClient(admin_env["base"])
    resp = client.login()
    assert resp.status in (200, 303)
    # CSRF 缺失 → 403（确认路由拒绝无凭证 POST）
    with pytest.raises(urllib.error.HTTPError) as exc:
        client.post("/admin/confirmations/FAKE/confirm", {})
    assert exc.value.code == 403, "无 CSRF 的确认 POST 必须被拒"


@pytest.mark.parametrize("origin", [
    "http://evil.example",                    # 完全外部源
    "http://evil-127.0.0.1.example",          # 后缀匹配放过的绕过（本次修复点）
    "http://127.0.0.1.evil.example",          # 前缀伪装
    "http://localhost:1",                     # 回环名但端口不符
    "https://127.0.0.1:9999",                 # 回环名但端口不符
])
def test_admin_cross_origin_rejected(admin_env, origin):
    """跨源 POST 必须被拒（§17.2）——按解析后的 host 精确比对，不做后缀匹配。"""
    client = AdminClient(admin_env["base"])
    client.login()
    with pytest.raises(urllib.error.HTTPError) as exc:
        client.post("/admin/confirmations/FAKE/confirm", {"csrf": client.csrf()},
                    origin=origin)
    assert exc.value.code == 403, origin
    assert "Origin check failed" in exc.value.read().decode()


def test_admin_same_origin_passes_origin_check(admin_env):
    """同源 POST 不被 Origin 挡下：走到 CSRF 分支（403，但失败原因是 CSRF 而非 Origin）。"""
    client = AdminClient(admin_env["base"])
    client.login()
    with pytest.raises(urllib.error.HTTPError) as exc:
        client.post("/admin/confirmations/FAKE/confirm", {},
                    origin=f"http://127.0.0.1:{ADMIN_PORT}")
    assert exc.value.code == 403
    body = exc.value.read().decode()
    assert "CSRF check failed" in body and "Origin check failed" not in body


def test_admin_same_origin_confirmation_end_to_end(admin_env):
    """同源 + 有效 CSRF：确认路由真正生效（303 → 待确认页），映射版本落库为 CONFIRMED。"""
    header = HEADERS["bill"]
    svc = ReconciliationService(str(admin_env["root"]))
    try:
        case = svc.freight_create_case("同源确认", "C-SAME", "2026-09-01T00:00:00+08:00",
                                       "2026-10-01T00:00:00+08:00")
        prep = svc.freight_prepare_mapping(case["id"], "bill", header)
    finally:
        svc.close()
    client = AdminClient(admin_env["base"])
    client.login()
    token = client.csrf()
    assert token, "待确认页应带 CSRF 表单"
    resp = client.post(f"/admin/confirmations/{prep['confirmation_id']}/confirm",
                       {"csrf": token}, origin=f"http://127.0.0.1:{ADMIN_PORT}")
    assert resp.status == 200  # 303 → 待确认页
    body = resp.read().decode()
    assert "Pending confirmations" in body
    assert prep["confirmation_id"] not in body, "确认过的请求仍在待确认页上（幽灵条目）"
    svc = ReconciliationService(str(admin_env["root"]))
    try:
        row = svc.db.conn.execute(
            "SELECT status FROM mapping_versions WHERE case_id=? AND kind='bill'",
            (case["id"],)).fetchone()
        assert row["status"] == "CONFIRMED", "同源确认必须真正激活映射版本"
        req = svc.db.conn.execute(
            "SELECT status FROM confirmation_requests WHERE id=?",
            (prep["confirmation_id"],)).fetchone()
        assert req["status"] == "CONFIRMED", "确认过的请求行必须落 CONFIRMED"
    finally:
        svc.close()


def test_admin_pages_render(admin_env):
    """用 Core 建一个案件后，管理页页面可渲染。"""
    client = AdminClient(admin_env["base"])
    client.login()
    client.get("/")
    svc = ReconciliationService(str(admin_env["root"]))
    case = svc.freight_create_case("页面渲染", "C1", "2026-09-01T00:00:00+08:00",
                                   "2026-10-01T00:00:00+08:00")
    svc.close()
    assert client.get("/admin/confirmations").status == 200
    assert client.get(f"/cases/{case['id']}/versions").status == 200


def test_admin_pages_escape_model_supplied_text(admin_env):
    """案件标题是模型可控文本：必须转义，不得成为可执行标记。"""
    payload = "<script>alert(1)</script>"
    svc = ReconciliationService(str(admin_env["root"]))
    try:
        case = svc.freight_create_case(payload, "C-XSS", "2026-09-01T00:00:00+08:00",
                                       "2026-10-01T00:00:00+08:00")
    finally:
        svc.close()
    client = AdminClient(admin_env["base"])
    client.login()
    for path in ("/", f"/cases/{case['id']}"):
        body = client.text(path)
        assert payload not in body, path
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body, path


def test_admin_pages_escape_asset_file_name(admin_env, tmp_path):
    """资产文件名同样来自本地文件：页面只显示转义文本。"""
    header = HEADERS["bill"]
    nasty = tmp_path / '<img src=x onerror="alert(1)">.csv'
    write_csv(nasty, header, [{"line_id": "L1", "carrier_id": "C-NAME", "trip_ref": "T1",
                               "service_leg_id": "LEG-1", "charge_code": "BASE",
                               "occurrence_id": "BASE", "amount_minor": "100",
                               "currency": "CNY", "amount_basis": "GROSS",
                               "reversal_of": ""}])
    svc = ReconciliationService(str(admin_env["root"]))
    try:
        case = svc.freight_create_case("文件名转义", "C-NAME", "2026-09-01T00:00:00+08:00",
                                       "2026-10-01T00:00:00+08:00")
        prep = svc.freight_prepare_mapping(case["id"], "bill", header)
        svc.admin_confirm(prep["confirmation_id"])
        asset = svc.freight_register_asset(case["id"], str(nasty), "bill")
        assert "<img" in asset["original_name"], "文件名应原样入库，仅在渲染层转义"
    finally:
        svc.close()
    client = AdminClient(admin_env["base"])
    client.login()
    body = client.text(f"/cases/{case['id']}")
    assert "Amount integrity" in body, "应已登录并渲染案件详情页"
    assert "<img src=x onerror=" not in body
    assert "&lt;img src=x onerror=" in body


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
