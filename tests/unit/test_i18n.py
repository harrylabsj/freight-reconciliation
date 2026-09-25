"""界面文案语言解析 + MCP 工具描述语言（目录要求英文默认、中文备用）。

覆盖 2026-09-24 复审提出的「UI strings 英文默认」要求：管理页可见文案与 MCP 工具描述
默认英文，中文经 Accept-Language（管理页）/ FREIGHT_LANG / 进程 locale（连接器）切换。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from adapters.mcp_server import TOOL_NAMES, McpServer  # noqa: E402
from freight_core.i18n import MESSAGES, resolve_lang, t, tool_description  # noqa: E402
from freight_core.service import ReconciliationService  # noqa: E402


def test_default_language_is_english():
    assert resolve_lang(None, env={}) == "en"          # 无任何线索 → 英文
    assert resolve_lang(None, env={"LANG": "en_US.UTF-8"}) == "en"
    assert resolve_lang("", env={}) == "en"
    assert resolve_lang("de-DE,fr;q=0.8", env={}) == "en"  # 不支持的语言 → 英文


def test_language_precedence():
    assert resolve_lang("zh-CN,zh;q=0.9,en;q=0.8", env={}) == "zh"      # Accept-Language
    assert resolve_lang("en-US,en;q=0.9", env={"LANG": "zh_CN.UTF-8"}) == "en"
    assert resolve_lang(None, env={"LANG": "zh_CN.UTF-8"}) == "zh"      # 进程 locale
    assert resolve_lang(None, env={"LC_ALL": "zh_CN.UTF-8"}) == "zh"
    assert resolve_lang(None, env={"FREIGHT_LANG": "zh"}) == "zh"       # 显式覆盖
    assert resolve_lang("zh-CN", env={"FREIGHT_LANG": "en"}) == "en"    # 覆盖优先于请求头
    assert resolve_lang("zh;q=0,en;q=0.5", env={}) == "en"              # q=0 视为不可用


def test_every_message_has_both_languages():
    assert MESSAGES, "文案表不得为空"
    for key, entry in MESSAGES.items():
        assert entry.get("en"), f"{key} 缺英文"
        assert entry.get("zh"), f"{key} 缺中文"


def test_missing_key_does_not_break_rendering():
    assert t("no.such.key", "en") == "no.such.key"
    assert t("login.submit", "en") == "Sign in"
    assert t("login.submit", "zh") == "登录"


def test_tool_descriptions_english_default_chinese_alternate():
    assert len(TOOL_NAMES) == 14
    for name in TOOL_NAMES:
        en, zh = tool_description(name), tool_description(name, "zh")
        assert en.isascii(), f"{name} 英文默认含非 ASCII"
        assert not zh.isascii(), f"{name} 中文备用缺失"
        assert en != zh


def test_mcp_tools_list_follows_language(tmp_path, monkeypatch):
    svc = ReconciliationService(str(tmp_path / "ws"), workspace_id="WS-LANG")
    try:
        def list_tools() -> list[dict]:
            server = McpServer(service=svc)
            result = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            assert result is not None
            return result["result"]["tools"]

        monkeypatch.setenv("FREIGHT_LANG", "en")
        tools_en = list_tools()
        assert len(tools_en) == len(TOOL_NAMES)
        assert all(tool["description"].isascii() for tool in tools_en)

        monkeypatch.setenv("FREIGHT_LANG", "zh")
        tools_zh = list_tools()
        assert all(not tool["description"].isascii() for tool in tools_zh)
        assert [tool["name"] for tool in tools_zh] == [tool["name"] for tool in tools_en]
    finally:
        svc.close()
