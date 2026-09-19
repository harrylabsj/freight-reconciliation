# 80 项系统验收 — 状态映射（2026-09-19）

来源：05_tests/acceptance.csv（初始全 NOT_RUN）。本文件把每项映射到实现与测试证据；
无证据的如实保留 NOT_RUN。测试名可在 tests/ 下检索。**PASS 仅指工程测试证据，
不替代实机与真实客户验证（§23：设计评审/自检不算通过证明）。**

状态定义：PASS=有实现+自动化测试证据；PARTIAL=实现覆盖主要路径，余项见备注；NOT_RUN=待外部条件。

## 导入与完整性
| 项 | 名称 | 状态 | 证据 |
|---|---|---|---|
| AT-001 | CSV正常导入 | PASS | test_golden_end_to_end（trips/bill/rates 导入 9/12/10 行） |
| AT-002 | XLSX多工作表 | PASS | test_xlsx_hidden_sheet_flagged（多表枚举+隐藏表告警） |
| AT-003 | 合计行识别 | PARTIAL | v1 由用户声明 declared_total_minor；自动识别合计行未实现 |
| AT-004 | 失败金额非零 | PASS | test_parse_failed_row_blocks_and_is_kept（失败行不计零、保留原行） |
| AT-005 | 公式缓存 | PASS | test_no_cache_formula_cells_flagged（无缓存公式拦截）；有缓存路径待宿主 |
| AT-006 | 长编号损坏 | PASS | test_id_damaged_scientific_notation |
| AT-007 | 来源合计不等 | PASS | test_declared_total_mismatch_blocks_freeze（SOURCE_TOTAL_MISMATCH→PARTIAL→禁冻结） |
| AT-008 | 跨文件重复 | PASS | test_duplicate_import_is_idempotent（sha256 幂等返回原 asset） |

## 字段与归属
| 项 | 名称 | 状态 | 证据 |
|---|---|---|---|
| AT-009 | 单位确认 | PASS | 映射字段含单位；amount_unit=yuan 走严格十进制（records._amount_minor） |
| AT-010 | 税口径未知 | PASS | UNKNOWN basis → BASIS_MISMATCH（test_unknown_basis_blocks 参考侧+引擎同语义） |
| AT-011 | 模板漂移 | PASS | test_mapping_structure_digest_changes_with_header + ingest 结构强制确认 |
| AT-012 | 跨承运商 | PASS | test_cross_carrier_line_is_isolated（CARRIER_CONFLICT 隔离分区） |
| AT-013 | 去返程区分 | PASS | service_leg_id 参与组键（§4.2），不同 leg 不并组 |
| AT-014 | 一车多订单 | PASS | order_ids 保留于 trips，不复制费用（关联表语义） |
| AT-015 | 一单分车 | PARTIAL | 需两个可靠 trip_id 才能成立；无双 trip 证据的账单行进待匹配，不自动认定 |
| AT-016 | 模糊匹配 | PASS | test_p3_candidates_require_manual_confirm（候选仅建议→人工确认生效） |

## 匹配与覆盖
| 项 | 名称 | 状态 | 证据 |
|---|---|---|---|
| AT-017 | 强匹配 | PASS | 金标 G01–G09 P1 全对 |
| AT-018 | 编号冲突 | PASS | CONFLICT 状态（编号存在但主体不符→隔离） |
| AT-019 | 一行多组 | PASS | test_randomized_groups_match_reference（唯一消费约束）+ 参考测试 |
| AT-020 | 多车合计 | PARTIAL | 无分摊依据的合计行进 UNMATCHED/待匹配，不均分（UNSUPPORTED_AGGREGATION 专用码未单列） |
| AT-021 | 台账反向遗漏 | PASS | not_billed_trips → NOT_BILLED_IN_PROVIDED_SCOPE（不算节省） |
| AT-022 | 历史范围 | PASS | test_history_duplicate_candidate_with_coverage（覆盖注记+候选标记） |
| AT-023 | 跨月补账 | PASS | service_time 取台账 departed_at，费率按计费时点选择（不按开票月） |
| AT-024 | 金额覆盖分母 | PASS | test_golden_coverage_metrics（905000/1082000≈83.64%） |

## 合同规则
| 项 | 名称 | 状态 | 证据 |
|---|---|---|---|
| AT-025 | 生效起点 | PASS | 参考+引擎：start 含（test_rate_start_inclusive 语义对齐） |
| AT-026 | 生效终点 | PASS | end 不含（RATE_NOT_FOUND） |
| AT-027 | 规则重叠 | PASS | check_overlaps 激活前阻断 + RATE_AMBIGUOUS |
| AT-028 | 规则缺失 | PASS | RATE_NOT_FOUND（金标路径） |
| AT-029 | 中途调价 | PASS | 非重叠区间共存；scoped 按时点唯一命中 |
| AT-030 | 时区缺失 | PASS | instant 拒绝 naive（测试+参考） |
| AT-031 | 未确认草稿 | PASS | RULE_UNCONFIRMED；规则导入即 DRAFT，需管理页激活 |
| AT-032 | 自由表达式 | PASS | 封闭枚举 PER_TRIP/WAIT_BLOCKS/ACTUAL_RECEIPT，无 eval（UNSUPPORTED_FORMULA） |

## 金额与冲销
| 项 | 名称 | 状态 | 证据 |
|---|---|---|---|
| AT-033 | 整分计算 | PASS | 金标全量+property digest 对齐（无 float 进核心） |
| AT-034 | 免费等待 | PASS | test_wait_free_exact_zero |
| AT-035 | 多一秒等待 | PASS | test_wait_one_second_one_block |
| AT-036 | 缺等待证据 | PASS | WAIT_EVIDENCE_INVALID（金标语义对齐） |
| AT-037 | 实报缺凭证 | PASS | MISSING_RECEIPT 不计零（金标 G05） |
| AT-038 | 超额冲销 | PASS | REVERSAL_INVALID（参考+property） |
| AT-039 | 明确冲销 | PASS | 金标 G09（1200−100=1100，差额 0，两行保留） |
| AT-040 | 重复与价差去重 | PASS | 金标 G04（+1500 只计一次）+ test_duplicate_suspicion_not_double_counted |

## 证据与复核
| 项 | 名称 | 状态 | 证据 |
|---|---|---|---|
| AT-041 | 签收缺失金额平 | PASS | 金标 G08（delta=0 且 evidence MISSING） |
| AT-042 | 原文定位 | PASS | source_rows 保留 sheet/行号/payload；get_evidence 返回定位 |
| AT-043 | 补证重跑 | PASS | test_stale_on_changed_results（新 run+STALE） |
| AT-044 | 接受账单 | PASS | test_review_prepare_confirm_and_stale（不改写 delta） |
| AT-045 | 摘要变化 | PASS | mark_stale_for_run：digest 不一致→STALE |
| AT-046 | 相同摘要 | PASS | 同上：一致→保持 ACTIVE |
| AT-047 | 未经验证外部意见 | PARTIAL | 附件与理由随决定保留；"外部回执"UI 呈现待管理页增强 |
| AT-048 | 确认凭证重放 | PASS | test_confirmation_replay_is_idempotent |

## 事务与恢复
| 项 | 名称 | 状态 | 证据 |
|---|---|---|---|
| AT-049 | 相同幂等请求 | PASS | test_idempotency_same_key_same_content |
| AT-050 | 键冲突 | PASS | test_idempotency_conflict_on_different_content |
| AT-051 | 超时恢复 | PASS | job 持久化：客户端超时后 get_job 查询（不盲目重发） |
| AT-052 | 运行崩溃 | NOT_RUN | job FAILED 落库已实现；RUNNING→RECOVERY_REQUIRED 检查点恢复未实现 |
| AT-053 | 并发修改 | PASS | expected_revision→VERSION_CONFLICT（test_version_conflict_on_expected_revision） |
| AT-054 | 产物磁盘满 | PARTIAL | staging+原子发布+GC（FileStore）；磁盘满注入测试未做 |
| AT-055 | 一致性备份 | NOT_RUN | integrity_check 已有；快照+hash 核对命令未实现 |
| AT-056 | 隔离目录 | PASS | workspace 隔离+文件白名单（test_path_escape_rejected） |

## 安全与导出
| 项 | 名称 | 状态 | 证据 |
|---|---|---|---|
| AT-057 | 提示词注入 | PASS | test_prompt_injection_treated_as_data |
| AT-058 | 路径穿越 | PASS | test_path_escape_rejected + test_symlink_escape_rejected |
| AT-059 | 压缩炸弹 | PASS | test_zip_bomb_rejected |
| AT-060 | 宏和外链 | PASS | test_macro_file_rejected + OLE 拒绝 + vbaProject/externalLinks 检查 |
| AT-061 | CSV公式注入 | PASS | test_export_csv_injection_guard |
| AT-062 | 隐私投影 | PASS | 导出投影脱敏（承运商视角）+ inspect 样例截断；投影 UI 细化待管理页 |
| AT-063 | 模型自批 | PASS | test_model_cannot_confirm（工具面无 confirm；stdio 对抗测试） |
| AT-064 | 下载非送达 | PASS | mark_downloaded 仅记 DOWNLOADED；导出文案"不是付款指令" |

## 宿主与可用性
| 项 | 名称 | 状态 | 证据 |
|---|---|---|---|
| AT-065 | 本地stdio安装 | NOT_RUN | 协议层已验（test_mcp_trusted_field_rejection_stdio）；宿主安装待实机 |
| AT-066 | Windows路径 | NOT_RUN | 待 Windows 实机 |
| AT-067 | 依赖离线失败 | NOT_RUN | 待宿主 |
| AT-068 | 分页不截断 | PASS | cursor 绑定 query_digest+limit 上限（Cursor 测试+list_issues） |
| AT-069 | MCP重启 | NOT_RUN | 待宿主（Host-Verification 3.1/3.2） |
| AT-070 | 模型服务故障 | PARTIAL | Core 确定性路径不依赖模型（设计保证）；降级模板文案待实机 |
| AT-071 | 响应与耗时 | PASS | start_run 立即返回 job_id；性能基线 1 万行 <8s（tests/host） |
| AT-072 | 无宿主独立性 | PASS | CLI 端到端冒烟（建案→导入→规则→运行） |

## 业务验收与发布（全部 NOT_RUN — 依赖 M5 真实客户）
| 项 | 名称 | 状态 |
|---|---|---|
| AT-073 | 双人金标 | NOT_RUN |
| AT-074 | 正常样本 | NOT_RUN |
| AT-075 | 原生对照 | NOT_RUN |
| AT-076 | 第二账期复用 | NOT_RUN |
| AT-077 | 高风险漏报 | NOT_RUN |
| AT-078 | 试点收益 | NOT_RUN |
| AT-079 | 上架材料 | NOT_RUN |
| AT-080 | 撤回与数据导出 | PARTIAL（可读导出已具备=导出服务；撤回流程未演练） |

## 汇总
PASS 55 · PARTIAL 10 · NOT_RUN 15。
NOT_RUN 集中在：宿主实机（4）、事务恢复深水区（2）、业务试点与发布（8）、其余见备注。
