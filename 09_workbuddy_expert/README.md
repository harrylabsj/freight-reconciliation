# 海纳·运费对账 — WorkBuddy 专家定稿（v0.2.0）

本目录是针对已实现 Core（src/freight_core + adapters）的专家资产定稿；`06_workbuddy_drafts/` 保持交接基线不动。
仍非可上架成品：无平台 asset_id、无市场图标、连接器打包与实机联调见 HOST-VERIFICATION.md（全部 NOT_RUN）。

```
09_workbuddy_expert/
├── expert/AGENT.md                     专家正文定稿
├── skills/freight-intake-and-rules/SKILL.md     导入与口径确认
├── skills/freight-reconcile-and-explain/SKILL.md 运行与差异解释
├── skills/freight-review-and-export/SKILL.md    补证复核与导出
├── connector/mcp-connector.json        本地 stdio 连接器声明草稿
└── HOST-VERIFICATION.md                WorkBuddy 实机验证清单（§18.2，初始 NOT_RUN）
```

首版路径（§18.2）：本地 Core → stdio MCP 连接器（adapters/mcp_server.py，14 工具）→ 一个专家依赖该连接器。
模型可 prepare 映射/规则/关联/复核/导出；人工确认只在本地管理页（adapters/admin_server.py）。
Buddy 应用封装后置（§18.3），需试点显示重复使用依据。
