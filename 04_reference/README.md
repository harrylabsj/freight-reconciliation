# 参考实现范围

运行：`python 04_reference/reference_engine.py 03_examples/normalized-groups.json`。
核查：`python 05_tests/test_reference.py`（需要jsonschema；本次环境已执行）。

仅实现规范化组的整分运算、三公式、规则唯一选择、当前组冲销、少量异常和覆盖汇总。没有真实文件解析、来源真实性核验、持久化、鉴权、复核页面、导出与WorkBuddy。输入必须先按候选Schema验证；reference_engine.py不是外部不可信输入安全边界。

归一化fixture中verified/confirmed为模拟的人审结果，不表示参考代码完成了身份与证据校验。生产版必须由认证状态服务提供这些字段，不接受模型自报true。
