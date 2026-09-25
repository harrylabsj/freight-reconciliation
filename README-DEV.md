# 海纳·运费对账 — 开发者快速上手（README-DEV）

生产主体在 `src/freight_core/`；交接包基线见根 README.md。本文件只讲怎么跑起来。

## 环境

```bash
python3 -m venv .venv
.venv/bin/pip install -r 05_tests/requirements-locked.txt pytest
```

要求 Python ≥3.11（开发验证于 3.14.5，见 06_development/runtime-decisions.md）。

## 三条验证命令（对应交接包 README 的自检）

```bash
.venv/bin/python 04_reference/reference_engine.py 03_examples/normalized-groups.json
.venv/bin/python 05_tests/test_reference.py          # 64 项，fail-fast 要求 rfc3339-validator
python3 08_verification/verify_manifest.py           # mismatch 恰好=HANDOFF_DELTA 已登记 2 文件
```

## 生产测试

```bash
.venv/bin/python -m pytest tests -q                  # 当前测试总数以输出为准
```

分层：unit / property（与参考引擎对齐）/ integration（金标端到端）/ security / integrity / host。

## 跑通一个案件（CLI）

```bash
export FREIGHT_RECON_ROOT=/tmp/freight_ws
C=$(.venv/bin/python -c "
import sqlite3,subprocess,sys
# 先建案
")
.venv/bin/python adapters/cli.py create-case --title 9月 --carrier C-DEMO \
  --period-from 2026-09-01T00:00:00+08:00 --period-to 2026-10-01T00:00:00+08:00
# 之后 confirm-mapping → register ×N → prepare-rules → run → summary → issues → freeze → export
# 完整脚本化示例见 tests/integration/test_golden_e2e.py 与 tests/conftest.py::golden_case
```

## 两个服务

- **MCP 连接器**（WorkBuddy 专家依赖）：`PYTHONPATH=src .venv/bin/python adapters/mcp_server.py`
  （stdio，14 工具；长任务返回 job_id 轮询）
- **本地管理页**（人类唯一确认入口）：`FREIGHT_ADMIN_TOKEN=口令 PYTHONPATH=src \
  .venv/bin/python adapters/admin_server.py` → http://127.0.0.1:8765/
  （仅 127.0.0.1；会话+CSRF+Origin 检查；prepare/confirm 分离）

## 界面语言（英文默认，中文备用）

文案表在 `src/freight_core/i18n.py`；解析顺序 FREIGHT_LANG → Accept-Language（管理页逐请求）
→ LC_ALL/LC_MESSAGES/LANG → 英文。管理页每请求按 `Accept-Language` 切换（中文浏览器自动中文），
连接器无逐请求语言通道，进程启动时解析一次。`FREIGHT_LANG=zh` 可强制中文。

界面所有插值一律经 `html.escape`（`admin_server.e()`）：案件标题、资产文件名、issue 文案、
决定理由等模型/账单可控文本绝不裸插 HTML。同源校验按解析后的 host 精确比对
（不做后缀匹配，端口必须等于监听端口）。

## 目录

```
src/freight_core/      Core：ingest/mapping/matching/rules/pricing/reconcile/review/export/storage
adapters/              mcp_server.py（连接器）· admin_server.py（管理页）· cli.py（回归）
tests/                 unit·property·integration·security·integrity·host
09_workbuddy_expert/   专家正文+三技能定稿+连接器声明+实机验证清单
06_development/        PROGRESS·ACCEPTANCE-STATUS·HANDOFF_DELTA·runtime-decisions
02_contracts/          8 份 JSON Schema + 14 个 MCP 工具输入契约（交接基线）
```

## 纪律

- 金额一律整数分；时间一律带时区 ISO；未知一律 null 不写 0。
- 模型只 prepare；confirm 只在管理页。manifest 不重写，交接包改动登记 HANDOFF_DELTA。
- 数值/金额规则变更必须先补契约与金标再实现（backlog 变更纪律）。
