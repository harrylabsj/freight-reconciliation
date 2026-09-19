"""HV 实机发现的连接器健壮性回归（M4 实测缺陷）。

背景：真实宿主运行中模型把 header 传成 JSON 字符串、fields 传成 list-of-dicts，
导致 prepare_mapping 抛 AttributeError 且连接器进程死亡（"freight MCP 服务已崩溃"）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from adapters.mcp_server import McpServer  # noqa: E402

from freight_core.service import ReconciliationService  # noqa: E402


def mk_server(tmp_path):
    svc = ReconciliationService(str(tmp_path / "ws"), workspace_id="WS-T")
    return McpServer(service=svc), svc


def call(server, name, args):
    r = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": args}})
    return json.loads(r["result"]["content"][0]["text"]), r["result"].get("isError")


def test_header_as_json_string_and_fields_as_list(tmp_path):
    """曾致连接器崩溃的参数形态：现在矫正后正常出映射候选。"""
    server, svc = mk_server(tmp_path)
    env, err = call(server, "freight_create_case", {
        "title": "t", "carrier_id": "C1",
        "period_from": "2026-09-01T00:00:00+08:00",
        "period_to": "2026-10-01T00:00:00+08:00"})
    cid = env["case_id"]
    env, err = call(server, "freight_prepare_mapping", {
        "case_id": cid, "kind": "BILL",
        "header": json.dumps(["line_id", "amount_minor"]),
        "fields": [{"source_column": "line_id", "target_field": "line_id"},
                   {"source_column": "amount_minor", "target_field": "amount_minor"}]})
    assert err is False and env.get("error") is None
    assert env["data"]["id"].endswith("bill#v1")
    svc.close()


def test_kind_case_normalized(tmp_path):
    server, svc = mk_server(tmp_path)
    env, err = call(server, "freight_create_case", {
        "title": "t", "carrier_id": "C1",
        "period_from": "2026-09-01T00:00:00+08:00",
        "period_to": "2026-10-01T00:00:00+08:00"})
    env, err = call(server, "freight_prepare_mapping", {
        "case_id": env["case_id"], "kind": "RATES", "header": ["rule_id", "version"]})
    assert err is False
    svc.close()


def test_confirm_kwarg_rejected(tmp_path):
    """模型尝试 confirm="true" 自批 → 受信字段拒收（§12.2）。"""
    server, svc = mk_server(tmp_path)
    env, _ = call(server, "freight_create_case", {
        "title": "t", "carrier_id": "C1",
        "period_from": "2026-09-01T00:00:00+08:00",
        "period_to": "2026-10-01T00:00:00+08:00"})
    env, err = call(server, "freight_prepare_mapping", {
        "case_id": env["case_id"], "kind": "bill", "header": ["x"], "confirm": "true"})
    assert err is True and env["error"]["code"] == "INVALID_INPUT"
    assert "confirm" in env["error"]["field_path"]
    svc.close()


def test_server_survives_bad_input(tmp_path):
    """任意坏参数（header=整数等）返回错误包络，进程与后续调用不受影响。"""
    server, svc = mk_server(tmp_path)
    env, _ = call(server, "freight_create_case", {
        "title": "t", "carrier_id": "C1",
        "period_from": "2026-09-01T00:00:00+08:00",
        "period_to": "2026-10-01T00:00:00+08:00"})
    cid = env["case_id"]
    bad, err = call(server, "freight_prepare_mapping",
                    {"case_id": cid, "kind": "bill", "header": 12345})
    assert err is True and bad["error"]["code"] in ("INVALID_INPUT", "INTERNAL")
    good, err = call(server, "freight_prepare_mapping",
                     {"case_id": cid, "kind": "bill", "header": ["a", "b"]})
    assert err is False and good.get("error") is None
    svc.close()
