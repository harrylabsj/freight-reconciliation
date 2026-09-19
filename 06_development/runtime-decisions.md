# 运行时决策记录（M0-D02）

| 项 | 决策 | 验证 |
|---|---|---|
| Python | 要求 ≥3.11；开发验证于 CPython 3.14.5（macOS arm64, darwin 27.0.0） | `python3 --version` |
| 依赖锁 | jsonschema==4.26.0 / rfc3339-validator==0.1.4 / openpyxl==3.1.5（05_tests/requirements-locked.txt，venv .venv） | pip install 成功 + 64 项测试 |
| date-time 严格检查 | 装载 rfc3339-validator 后 `'date-time' in FormatChecker().checkers == True`（未装时为 False，缺陷1实测） | 2026-09-19 本机 |
| MCP 接入 | 不引入 MCP SDK 依赖；adapters/mcp_server.py 以标准库实现 stdio 换行分隔 JSON-RPC 2.0（initialize / tools/list / tools/call），协议行为由 tests/host 断言 | 待 host 测试 |
| 管理页 | 标准库 http.server 本地服务，无 Web 框架；会话 cookie + CSRF token + 一次性确认凭证 | 待集成测试 |
| 数据库 | sqlite3 标准库，WAL 模式，仅本地盘；17 表 schema 见 src/freight_core/storage/db.py | 待集成测试 |
| XLSX | openpyxl 读写（MIT）；导入公式只用缓存值，导出值不写公式 | 待集成测试 |
| 时区 | 存储一律带偏移 ISO 串；展示用 zoneinfo Asia/Shanghai | 单测 |
