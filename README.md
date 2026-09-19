# 海纳·运费对账 — 设计交接包 v0.1.0

日期2026-09-19。这是设计基线、候选契约、合成样例、参考实现和开发验收清单，不是已完成产品或可直接上架的插件。

## 从这里开始
1. 阅读01_design中的主文档、implementation-backlog.md和data-dictionary.md。
2. 核对MANIFEST.sha256，跑下列参考测试。
3. 从M0收集真实授权样本、确认计费粒度并验证目标宿主；不得依据参考PASS宣布生产完成。

```bash
python 04_reference/reference_engine.py 03_examples/normalized-groups.json
python 05_tests/test_reference.py
python 08_verification/verify_manifest.py
```

参考引擎用Python标准库；Schema测试另需jsonschema，可运行 `python -m pip install -r 05_tests/requirements-reference.txt`。默认自检不改动本包文件；只有维护者显式传入 `--write-report` 才会更新测试报告，随后须重新生成文件清单。依赖声明只用于设计自检，生产开发须另锁版本和供应链。各引用路径相对本包根目录。

## 已提供
主设计Word与Markdown；8份候选JSON Schema及8组对象示例、14个拟新增MCP工具的输入契约；10组/12账单行合成场景、独立金标；参考引擎；64项参考与契约测试；80项系统验收规格；一个专家/三技能正文草稿；6份CSV输入模板、7工作表XLSX合成样例模板与字段解释；实际自检报告和文件摘要。

## 未完成
真实账单导入生产实现、完整权限与数据库、人工确认页面、MCP/连接器打包、真实Excel导出、WorkBuddy联调、客户试点、平台审核、付款或系统回写。80项系统验收初始均NOT_RUN。

所有客户、承运商、车型、运价和金额均为合成数据；名称未作最终品牌确认。示例SourceAsset/RunManifest里的重复字符哈希为明确占位值，不能冒充真实来源摘要。实际交付文件摘要仅见MANIFEST.sha256。

## 边界
与Kiwi独立，不复用其生产凭据、数据库或公共目录。固定线路按车次；基础费、按块等候费、有证实报费。先提供可追溯待核差异，不自动认定欠款，不自动扣款/付款/发送/回写。
