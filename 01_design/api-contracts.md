# 服务契约补充（候选，不是已部署API）

02_contracts/mcp-tools.draft.json包含14个工具输入Schema，严禁将这个JSON当成已经注册的MCP服务。
各工具在同一认证工作区执行；case/run/asset/job/issue全部验证归属，ID难猜不能代替鉴权。模型不得提交workspace、actor、confirmed、approval_token等受信字段。新对话通过本地案件选择器选择已有case/run，Core注入安全上下文；没有确认的案件不猜选最近一个。

## 响应
成功：`{schema_version, request_id, case_id, case_revision, data, warnings, coverage}`；没有case的对象可按其关联解析后填入。结构化data按相应领域契约投影，不向模型返回私密全文件或确认凭证。
失败：`{schema_version, request_id, error:{code,message,retryable,field_path,recovery_action}}`。与MCP isError一致；请求级错误不返回半个成功金额。

错误码：INVALID_INPUT、ACCESS_DENIED、NOT_FOUND、VERSION_CONFLICT、IDEMPOTENCY_CONFLICT、SOURCE_TOTAL_MISMATCH、RULE_UNCONFIRMED、RATE_AMBIGUOUS、JOB_PENDING、RECOVERY_REQUIRED、LIMIT_EXCEEDED、FEATURE_UNSUPPORTED。是否retryable由错误本身确定，金额口径错误不能通过重试解决。

分页cursor绑定query_digest、run_id和读取权限；limit默认50最大100。没有next_cursor代表当前查询完结，不代表客户数据总体完整。变更查询参数不得复用旧cursor。

## 管理确认
准备候选不激活。可信管理页POST确认时验证会话/CSRF/nonce、case revision、对象摘要、角色、有效期和单次凭证，在事务中写确认记录；GET没有副作用。重复同一已完成动作返回原结果，不创建第二个批准。规则、匹配、人工决定和冻结结果各自绑定摘要，互不代替。

## 幂等与等待
创建/登记/prepare/run均显式幂等键。同键不同参数报409语义冲突；已存在job返回原编号。工具需要长任务时立即返回job_id，不能把30秒超时当工作取消。实际HTTP映射、SDK版本和连接器安装在M0/M4另行冻结验证。
