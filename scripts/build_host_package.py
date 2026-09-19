#!/usr/bin/env python3
"""从 09_workbuddy_expert/ + src/ 确定性构建 WorkBuddy 宿主插件包（纯标准库）。

产出 dist/host-plugin/freight-reconciliation/，布局对齐平台包格式：
  .codebuddy-plugin/plugin.json   平台清单（expertType=agent）
  .mcp.json                       本地 stdio 连接器（${CODEBUDDY_PLUGIN_ROOT} 自定位）
  agents/freight-reconciliation.md 专家正文（frontmatter+正文）
  skills/<三技能>/SKILL.md
  engine/freight_core/            Core 副本（打包后自包含）
  engine/adapters/mcp_server.py   连接器代码副本
  engine/02_contracts/            工具输入契约副本（tools/list 用）
  engine/mcp_main.py              打包布局启动器
  scripts/mcp-stdio.sh            自定位执行壳（venv 优先 ~/.cache/freight-reconciliation）
  requirements.txt

构建不修改源码树；含本机绝对路径/占位符泄漏即失败。
可选 --setup-venv：创建 ~/.cache/freight-reconciliation/venv 并安装锁定依赖（宿主实机验证用）。
"""
from __future__ import annotations

import argparse
import json
import shutil
import stat
import struct
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "host-plugin" / "freight-reconciliation"
NAME = "freight-reconciliation"
VERSION = "0.2.0"

LEAK_PATTERNS = ("/Users/", "REPLACE_WITH_", "HANDOFF_DELTA", "MANIFEST.sha256")

SKILLS = ("freight-intake-and-rules", "freight-reconcile-and-explain",
          "freight-review-and-export")


def fail(msg: str) -> None:
    raise SystemExit(f"build_host_package: {msg}")


def copy_tree(src: Path, dst: Path) -> None:
    for item in src.rglob("*"):
        if "__pycache__" in item.parts or item.name == ".DS_Store":
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def tiny_png(path: Path) -> None:
    """生成 64x64 纯色 PNG 头像（占位，上架前替换正式视觉资产）。"""
    import zlib
    w = h = 64
    raw = b"".join(b"\x00" + b"\x1f\x4e\x5d" * w for _ in range(h))
    def chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    path.write_bytes(png)


def build() -> None:
    expert = ROOT / "09_workbuddy_expert"
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    # 1) agents/<name>.md：frontmatter + 专家正文
    agent_body = (expert / "expert" / "AGENT.md").read_text(encoding="utf-8")
    agent_body = agent_body.split("# 海纳·运费对账（专家正文）", 1)[1]
    agent_md = f"""---
name: {NAME}
description: Payer-side freight reconciliation expert: import, deterministic re-calculation, evidence-linked differences. Not a payment approver.
displayName:
  zh: 海纳·运费对账
  en: Haina · Freight Reconciliation
profession:
  zh: 物流运费对账专家
  en: Freight Reconciliation Expert
maxTurns: 40
skills:
  - freight-intake-and-rules
  - freight-reconcile-and-explain
  - freight-review-and-export
---
# 海纳·运费对账（专家正文）{agent_body}"""
    (OUT / "agents").mkdir()
    (OUT / "agents" / f"{NAME}.md").write_text(agent_md, encoding="utf-8")

    # 2) skills/
    for skill in SKILLS:
        copy_tree(expert / "skills" / skill, OUT / "skills" / skill)

    # 3) engine/：Core + 连接器 + 契约
    copy_tree(ROOT / "src" / "freight_core", OUT / "engine" / "freight_core")
    copy_tree(ROOT / "02_contracts", OUT / "engine" / "02_contracts")
    (OUT / "engine" / "adapters").mkdir()
    (OUT / "engine" / "adapters" / "__init__.py").write_text("", encoding="utf-8")
    shutil.copy2(ROOT / "adapters" / "mcp_server.py",
                 OUT / "engine" / "adapters" / "mcp_server.py")
    (OUT / "engine" / "mcp_main.py").write_text(
        '"""打包布局启动器：engine/ 即 sys.path 根（构建时生成，勿手改）。"""\n'
        "import sys\n"
        "from pathlib import Path\n"
        "ENGINE = Path(__file__).resolve().parent\n"
        "for p in (str(ENGINE),):\n"
        "    if p not in sys.path:\n"
        "        sys.path.insert(0, p)\n"
        "from adapters.mcp_server import main\n\n"
        'if __name__ == "__main__":\n'
        "    main()\n",
        encoding="utf-8")

    # 4) 自定位执行壳
    scripts = OUT / "scripts"
    scripts.mkdir()
    sh = scripts / "mcp-stdio.sh"
    sh.write_text(
        "#!/bin/bash\n"
        "# 自定位：依赖 ${CODEBUDDY_PLUGIN_ROOT} 注入；直跑时按脚本位置回退。\n"
        'if [ -n "${CODEBUDDY_PLUGIN_ROOT:-}" ] && [ -d "${CODEBUDDY_PLUGIN_ROOT}/engine" ]; then\n'
        '  ROOT="${CODEBUDDY_PLUGIN_ROOT}"\n'
        "else\n"
        '  SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        '  ROOT="$(dirname "$SELF")"\n'
        "fi\n"
        'PY="${FREIGHT_PYTHON:-}"\n'
        'if [ -z "$PY" ]; then\n'
        '  if [ -x "$HOME/.cache/freight-reconciliation/venv/bin/python" ]; then\n'
        '    PY="$HOME/.cache/freight-reconciliation/venv/bin/python"\n'
        "  else\n"
        '    PY="python3"\n'
        "  fi\n"
        "fi\n"
        'export FREIGHT_RECON_ROOT="${FREIGHT_RECON_ROOT:-$HOME/.local/share/freight-reconciliation}"\n'
        'exec "$PY" "$ROOT/engine/mcp_main.py"\n',
        encoding="utf-8")
    sh.chmod(sh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # 5) .mcp.json（stdio，自定位）
    (OUT / ".mcp.json").write_text(json.dumps({
        "mcpServers": {NAME: {
            "type": "stdio",
            "command": "${CODEBUDDY_PLUGIN_ROOT}/scripts/mcp-stdio.sh",
            "args": [],
            "env": {},
            "defer_loading": False,
        }}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 6) plugin.json
    plugin_json = {
        "name": NAME,
        "version": VERSION,
        "description": "Deterministic freight reconciliation core via local stdio MCP.",
        "author": {"name": "Haina"},
        "agents": [f"./agents/{NAME}.md"],
        "expertType": "agent",
        "agentName": NAME,
        "skills": [f"./skills/{s}" for s in SKILLS],
        "license": "MIT",
        "keywords": ["freight", "reconciliation", "logistics"],
        "displayName": {"zh": "海纳·运费对账", "en": "Haina · Freight Reconciliation"},
        "profession": {"zh": "物流运费对账专家", "en": "Freight Reconciliation Expert"},
        "displayDescription": {
            "zh": "把运输台账、承运商账单、确认合同费率与履约凭证核对成有依据、可复算、可复核的差异清单。不自动付款或发送。",
            "en": "Reconcile carrier bills against contracts and evidence; deterministic, auditable differences."},
        "avatar": "avatars/haina.png",
        "defaultInitPrompt": {"zh": "把承运商9月账单与运输台账核对。",
                              "en": "Reconcile this month's carrier bill."},
        "plugin": NAME,
        "tags": [{"zh": "运费对账", "en": "Freight Reconciliation"},
                 {"zh": "差异核对", "en": "Bill Differences"},
                 {"zh": "证据核查", "en": "Evidence Check"}],
        "quickPrompts": [
            {"zh": "把承运商9月账单与运输台账核对。", "en": "Reconcile the bill against trips."},
            {"zh": "为什么这次等待费多了50元？", "en": "Why is the waiting fee higher?"},
            {"zh": "生成发给承运商核对的材料。", "en": "Prepare the reconciliation material."}],
    }
    (OUT / ".codebuddy-plugin").mkdir()
    (OUT / ".codebuddy-plugin" / "plugin.json").write_text(
        json.dumps(plugin_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 7) 头像 / requirements / README
    avatars = OUT / "avatars"
    avatars.mkdir()
    tiny_png(avatars / "haina.png")
    (OUT / "requirements.txt").write_text(
        "jsonschema==4.26.0\nrfc3339-validator==0.1.4\nopenpyxl==3.1.5\n",
        encoding="utf-8")
    (OUT / "README.md").write_text(
        f"# {NAME} 宿主插件包 v{VERSION}\n\n由 scripts/build_host_package.py 确定性构建；"
        "勿手改。连接器为本地 stdio（engine/mcp_main.py），数据根默认"
        " ~/.local/share/freight-reconciliation（可用 FREIGHT_RECON_ROOT 覆盖）。\n",
        encoding="utf-8")

    # 8) 泄漏扫描（本机绝对路径/占位符）
    for f in OUT.rglob("*"):
        if f.is_file() and f.suffix in (".md", ".json", ".py", ".sh", ".txt"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            for pat in LEAK_PATTERNS:
                if pat in text:
                    fail(f"leak pattern {pat!r} in {f.relative_to(OUT)}")
    print(f"built: {OUT}")


def setup_venv() -> None:
    venv = Path.home() / ".cache" / "freight-reconciliation" / "venv"
    if not venv.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    subprocess.run([str(venv / "bin" / "pip"), "install", "-q",
                    "-r", str(OUT / "requirements.txt")], check=True)
    print(f"venv ready: {venv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup-venv", action="store_true")
    args = parser.parse_args()
    build()
    if args.setup_venv:
        setup_venv()
