# 数据字典与字段语义

本文件与02_contracts互补；标注的展示/持久字段不是模型可任意填写的鉴权字段。

|字段|含义|单位/来源/约束|
|---|---|---|
|workspace_id|一个经营主体的隔离空间|服务端会话确定，不信任工具输入|
|case_id|一个承运商账期核对案件|不可因更名换身份|
|trip_id|一次实际运输执行|不是订单数或付款笔数|
|service_leg_id|已确认运输段|去返程不得混并|
|occurrence_id|一次费用事件|基础费BASE；等待/票据事件有独立ID|
|bill_line_id/line_id|来源中一行费用|每run只可被消费一次|
|amount_minor|账单金额|整数分；正数收费，负数仅显式冲销|
|amount_basis|金额口径|GROSS已声明含税，NET未税，UNKNOWN阻断|
|service_time|合同约定的计费时点|含时区ISO时间；不以开票日替换|
|rule_id/version|已确认条款版本|规则范围不重叠，变更不覆盖旧版|
|effective_from/to|生效起止|左闭右开，必须有业务时区|
|formula|计价方式|PER_TRIP/WAIT_BLOCKS/ACTUAL_RECEIPT|
|rate_minor|每车次或每等待块单价|整数分；不是任意字符串公式|
|free_seconds|每事件免费秒数|不能未经合同把装卸合并|
|block_seconds|向上进位单位|正整数秒|
|cap_minor|凭证型费用上限|null无配置；0是明确0上限|
|reversal_of|被冲销原账单行|同案件同组正数行，累计不超原额|
|source_refs|原文件/单元格/页引用|原行号、范围和文件摘要共同确定|
|expected_minor|按确认规则的应计金额|无法确定为null，不是0|
|delta_minor|账单净额减应计|仅同口径且应计确定时计算|
|evidence_status|凭证充分性|与金额是否相等独立|
|result_digest|稳定结果摘要|不含生成时间；不能证明原始文件真实|
|review_decision|人的处置意见|不得改写expected/delta|

## 输入模板约定
CSV均为UTF-8 BOM；首行为技术列名。字符串编号保前导零。amount_minor/rate_minor明确为分，不能把元直接粘进去。XLSX模板的示例行仅教学，生产导入前需删除。bill的来源金额全部声明GROSS；G07的NET来自冲突合同规则，因此控制合计不会混加两种账单口径。

## 字段权威建议
trip/route/车型来自经营方执行台账；账单金额来自原始承运商明细；费率来自已确认合同；签收来自所提供履约凭证及人工核对；等待从确认事件时间计算；票据有效性由被授权的人确认。本系统不判定票据或签名真实性。

## 控制项
每次run保存输入总行数、可比/不可比/排除互斥行数、解析失败清单、有符号控制合计、绝对金额覆盖分母、历史覆盖说明。JSON Schema验证类型，不自动证明行间守恒/冲销关系/主体权限；这些由服务层和性质测试验证。
