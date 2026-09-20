# 开发进度（PROGRESS）

对照开发计划 `docs/海纳_物流运费对账_开发计划_v0.1.0.md` 与 implementation-backlog D01–D16。

| 阶段 | 状态 | 证据 |
|---|---|---|
| M0 事实与宿主验证（工程部分） | ✅ 完成 | 交接包落位+复检（§0）、缺陷 1–3 修复、64/64 复现、运行时决策 runtime-decisions.md；**客户访谈（T02/T03）外部事项未做** |
| M1 导入和口径 | ✅ 完成 | Ingestor（安全读取/限额/拒绝矩阵/原行定位）、MappingService（结构签名版本化）、控制总数与守恒；tests/unit+integration |
| M2 核算核心 | ✅ 完成 | 匹配 P1/P2/P3、核算组唯一消费、三公式、冲销/去重/唯一归集、异常码、金标 10 组端到端全对、性质测试与参考引擎 digest 级对齐、性能基线实测 1 万行 <8s（目标 60s） |
| M3 人工复核与导出 | ✅ 完成 | SQLite 17+2 表、状态机、五版本号、幂等键、STALE、prepare/confirm 分离、管理页五页面、冻结条件、XLSX 十表+MD 导出、CSV 注入防护、安全必测 |
| M4 WorkBuddy 专家 | ✅ 本机实机通过（7/7）/ ⏳ Windows+裸机待验 | codebuddy CLI 无头实机：连接器加载/召唤路由/登记/规则/job轮询金标一致/注入对抗/自批拒绝/受信字段拒收 全 PASS；实机发现并修复 4 缺陷（连接器崩溃、契约命名对齐、版本冲突恢复、凭证搜索防护）；余 Windows/裸机项 NOT_RUN |
| M5 客户平行试点 | ⛔ 未启动 | 外部依赖：真实客户样本、双人金标（§23.2/§24） |
| M6 上架/Buddy 评估 | ⏳ 专家已提审，尚未公开发布；Buddy 评估未启动 | 2026-09-20 提交 WorkBuddy 专家 v0.2.0，ID `oe_8b7cbde9e305a91d`，平台显示「审核中」；M5 客户平行试点仍未启动 |

## 测试与验证总账（2026-09-19）

| 套件 | 数量 | 状态 |
|---|---|---|
| 交接包参考+契约测试（05_tests/test_reference.py） | 64 | ✅ 全过（unittest 与 pytest 双运行器） |
| tests/unit（金额/时间/等候/映射签名） | 21 | ✅ |
| tests/property（参考引擎对齐/不变量/顺序/去重） | 6 | ✅ |
| tests/integration（金标端到端/控制/复核/冻结导出/幂等/隔离/候选/历史） | 20 | ✅ |
| tests/security（路径/宏/炸弹/公式/注入/自批/stdio 对抗） | 12 | ✅ |
| tests/integrity（HANDOFF_DELTA 双向断言） | 2 | ✅ |
| tests/host（管理页 HTTP/性能基线） | 5 | ✅ |
| **合计** | **130** | **全绿** |

## 诚实边界（未完成/未验证）

- WorkBuddy 本机已完成 codebuddy CLI 无头实机联调；Windows、全新裸机、WorkBuddy.app 交互界面和运行中断恢复仍待验证（详见 HOST-VERIFICATION.md）。
- 真实客户数据、双人真实金标、三方对照试点（M5）与上架材料（M6）。
- 运行崩溃后的 RECOVERY_REQUIRED 检查点恢复与一致性备份命令（AT-052/055）：文件层
  staging+原子发布+回收已实现，数据库恢复扫描器未实现。
- 隐藏行排除的"行号+原因+金额去向"登记 UI（读取侧已枚举并告警）。
- 合计行自动识别（AT-003）：v1 由用户经 declared_total_minor 声明，未做自动识别。
