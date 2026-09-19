# HANDOFF_DELTA — 交接包改动登记

规则：`MANIFEST.sha256` 与原样基线提交（16fbaf6）永不重写；对本包内文件的任何修改在此登记，并由测试双向断言（tests/integrity 包内改动均有 DELTA 条目）。

| # | 文件 | 类别 | 内容 | 依据 |
|---|---|---|---|---|
| 1 | 05_tests/requirements-reference.txt | 缺陷修复 | 补声明 `rfc3339-validator>=0.1.4,<0.2`。jsonschema 仅在 rfc3339-validator 可导入时注册严格 `date-time` 检查器；缺失时静默降级（本机实测：未装时 `date-time not in FormatChecker().checkers`）。 | travel-expert 同类缺陷；主设计 §8.1 要求带时区 ISO 时间 |
| 2 | 05_tests/test_reference.py | 缺陷修复 | ① 文件头增加 fail-fast：`date-time` 检查器未注册时以明确错误退出；② 动态测试改由工厂函数生成，消除模块级 `test` 泄漏（pytest 收集报 `fixture 'self' not found`）；测试数保持 64。 | 复检记录 2026-09-19 |
| 3 | 05_tests/requirements-locked.txt（新增） | 缺陷修复 | 锁定验证版本 jsonschema==4.26.0 / rfc3339-validator==0.1.4 / openpyxl==3.1.5。 | 缺陷 3（未锁版本） |
| 4 | 06_development/*（新增）、src/、adapters/、tests/、README-DEV.md、09_workbuddy_expert/*（新增） | 生产实现 | 按 implementation-backlog D02–D14 开发的新目录与文件，不属于交接包原文件。09_workbuddy_expert/ 为三技能与专家正文定稿（基线草稿 06_workbuddy_drafts/ 保持不动）。 | 开发计划 M0–M4 |
