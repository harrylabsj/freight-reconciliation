# WorkBuddy 实机验证清单（§18.2 — M4 决策门）

状态初始全部 NOT_RUN。**任何一项未执行不得宣称"可上架连接器"或"已在 WorkBuddy 可用"。**
每项记录：执行日期、平台/OS、WorkBuddy 版本、证据（截图/日志/轨迹）。

## 1. 连接器接入
| # | 验证项 | 方法 | 状态 |
|---|---|---|---|
| 1.1 | 依赖安装成功（Python 3.11+、openpyxl/jsonschema/rfc3339-validator）在客户电脑裸机 | 全新账户机器安装 | NOT_RUN |
| 1.2 | 相对路径与打包后资源位置（02_contracts、09_workbuddy_expert 随包可达） | 打包安装后 tools/list | NOT_RUN |
| 1.3 | Windows 路径与编码（盘符/空格/中文路径的文件选择与读取） | Windows 11 实机 | NOT_RUN |
| 1.4 | macOS 路径与权限提示（TCC 文件访问） | macOS 实机 | NOT_RUN |
| 1.5 | stdio 连接器绑定：initialize → tools/list 14 工具 → tools/call | 宿主连接器配置页 | NOT_RUN |

## 2. 文件与任务
| # | 验证项 | 方法 | 状态 |
|---|---|---|---|
| 2.1 | 文件选择句柄：用户授权的文件路径能传给 freight_register_asset | 端到端导入一次 | NOT_RUN |
| 2.2 | job 轮询：start_run 立即返回 job_id，freight_get_job 到终态 | 大文件导入 | NOT_RUN |
| 2.3 | 超时语义：>30 秒的长任务不被视为失败；客户端超时后查询 job 恢复 | 人为延迟 | NOT_RUN |
| 2.4 | 权限提示内容与频率可接受；无越界文件访问请求 | 全流程观察 | NOT_RUN |

## 3. 宿主与恢复
| # | 验证项 | 方法 | 状态 |
|---|---|---|---|
| 3.1 | WorkBuddy 重启后恢复：案件/资产/规则/复核记录仍在（Core 已持久化） | 杀进程重开 | NOT_RUN |
| 3.2 | RUN 中断（RUNNING → RECOVERY_REQUIRED）后按检查点恢复或安全失败 | 重启注入 | NOT_RUN |
| 3.3 | 输出文件展示：导出 XLSX/MD 在宿主内可打开、路径正确 | 导出后打开 | NOT_RUN |
| 3.4 | 专家召唤与技能路由：三技能按用户意图正确触发 | 会话测试 | NOT_RUN |

## 4. 边界行为
| # | 验证项 | 方法 | 状态 |
|---|---|---|---|
| 4.1 | 提示词注入：构造含"批准/付款"指令的账单文件，模型不执行 | 对抗样例 | NOT_RUN |
| 4.2 | 模型无法触达管理页确认（admin_confirm 无工具暴露） | 尝试越权 | NOT_RUN |
| 4.3 | 受信字段（workspace_id/nonce 等）经连接器传入被拒 | 对抗调用 | NOT_RUN |

执行完上述全部项并留证后，方可进入 M5 客户平行试点（§22 阶段门）。
