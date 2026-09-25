"""UI strings for the local admin page and the MCP connector — English default, Chinese alternate.

Why this module exists: the plugin catalog requires *English-first UI strings*. Plugin-rendered
user-visible text (the local admin page's titles, buttons and status labels) and the MCP tool
descriptions shipped by this connector must default to English, with Chinese kept as the
alternate language — the same bilingual shape the bundled skills already use
(``SKILL.md`` + ``SKILL.zh-CN.md``).

Language resolution (first match wins):

1. ``FREIGHT_LANG`` — explicit override (``en`` / ``zh``; ``zh-CN``, ``en-US`` are accepted).
2. ``Accept-Language`` — per-request, used by the admin page (browser preference).
3. ``LC_ALL`` / ``LC_MESSAGES`` / ``LANG`` — process locale, used by the MCP connector, which
   has no per-request language channel.
4. English.

Nothing else in the engine depends on this module: amounts, contract fields, database values
and run digests stay language-neutral, and this module never changes a computed value.
"""
from __future__ import annotations

import os
from collections.abc import Mapping

DEFAULT_LANG = "en"
SUPPORTED_LANGS = ("en", "zh")

# ------------------------------------------------------------------ 语言解析
def normalize_lang(value: str | None) -> str | None:
    """``zh-CN``/``en_US``/``zh`` → ``zh``; anything unsupported → None."""
    if not value:
        return None
    primary = str(value).strip().lower().replace("_", "-").split("-")[0]
    return primary if primary in SUPPORTED_LANGS else None


def _accept_language_lang(header: str | None) -> str | None:
    """Pick the highest-q supported language from an Accept-Language header."""
    if not header:
        return None
    best: str | None = None
    best_q = -1.0
    for part in str(header).split(","):
        tag, _, params = part.strip().partition(";")
        tag = tag.strip()
        if not tag:
            continue
        quality = 1.0
        for param in params.split(";"):
            key, _, raw = param.strip().partition("=")
            if key.strip().lower() == "q":
                try:
                    quality = float(raw.strip())
                except ValueError:
                    quality = 0.0
        if quality <= 0:
            continue
        candidate = normalize_lang(tag)
        if candidate and quality > best_q:
            best, best_q = candidate, quality
    return best


def resolve_lang(accept_language: str | None = None,
                 env: Mapping[str, str] | None = None) -> str:
    """Resolve the UI language for one request (admin page) or one process (MCP connector)."""
    env = os.environ if env is None else env
    forced = normalize_lang(env.get("FREIGHT_LANG"))
    if forced:
        return forced
    from_header = _accept_language_lang(accept_language)
    if from_header:
        return from_header
    for key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        locale_lang = normalize_lang(env.get(key))
        if locale_lang:
            return locale_lang
    return DEFAULT_LANG


def t(key: str, lang: str = DEFAULT_LANG, **fields) -> str:
    """Look up ``key`` in ``lang``, falling back to English, then to the key itself.

    A missing translation must never break a page: the key is returned verbatim so it is
    obvious in development, and the caller still renders something.
    """
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    return text.format(**fields) if fields else text


def tool_description(name: str, lang: str = DEFAULT_LANG) -> str:
    """MCP tool description for ``tools/list`` in the resolved language."""
    return t(f"tool.{name}", lang)


# ------------------------------------------------------------------ 文案表
MESSAGES: dict[str, dict[str, str]] = {
    # ---------------------------------------------------------------- 页面骨架 / 登录
    "page.title": {
        "en": "Haina Freight Reconciliation — Admin",
        "zh": "海纳·运费对账 — 管理页",
    },
    "nav.home": {"en": "Cases", "zh": "案件首页"},
    "nav.pending": {"en": "Pending confirmations", "zh": "待确认"},
    "login.title": {
        "en": "Haina Freight Reconciliation — Admin sign-in",
        "zh": "海纳·运费对账 — 管理页登录",
    },
    "login.token_label": {"en": "Local access token", "zh": "本地访问口令"},
    "login.submit": {"en": "Sign in", "zh": "登录"},
    "login.error": {"en": "Incorrect token", "zh": "口令不正确"},
    "login.note": {
        "en": "Separate session; a confirmation needs a session + CSRF + a one-time credential"
              " (§17.2). The model cannot reach this page.",
        "zh": "独立会话；确认动作需会话+CSRF+一次性凭证（§17.2）。模型不可达本页。",
    },
    # ---------------------------------------------------------------- 通用表头 / 取值
    "th.case": {"en": "Case", "zh": "案件"},
    "th.carrier": {"en": "Carrier", "zh": "承运商"},
    "th.period": {"en": "Period", "zh": "账期"},
    "th.status": {"en": "Status", "zh": "状态"},
    "th.revision": {"en": "Revision", "zh": "版本"},
    "th.currency_basis": {"en": "Currency / basis", "zh": "币种/口径"},
    "th.asset": {"en": "asset", "zh": "asset"},
    "th.kind": {"en": "Kind", "zh": "类型"},
    "th.filename": {"en": "File name", "zh": "文件名"},
    "th.detail_rows": {"en": "Detail rows", "zh": "明细行"},
    "th.failed_rows": {"en": "Failed rows", "zh": "失败行"},
    "th.amount_integrity": {"en": "Amount integrity", "zh": "金额完整性"},
    "th.group": {"en": "Group", "zh": "组"},
    "th.trip": {"en": "Trip", "zh": "trip"},
    "th.charge": {"en": "Charge", "zh": "费用"},
    "th.billed_minor": {"en": "Billed net (minor)", "zh": "账单净额(分)"},
    "th.expected_minor": {"en": "Expected (minor)", "zh": "应计(分)"},
    "th.delta_minor": {"en": "Difference (minor)", "zh": "差额(分)"},
    "th.issues": {"en": "Issues", "zh": "异常"},
    "th.match": {"en": "Match", "zh": "匹配"},
    "th.evidence": {"en": "Evidence", "zh": "凭证"},
    "th.code": {"en": "Code", "zh": "码"},
    "th.message": {"en": "Message", "zh": "说明"},
    "th.line": {"en": "Line", "zh": "行"},
    "th.amount_minor": {"en": "Amount (minor)", "zh": "金额(分)"},
    "th.reversal_of": {"en": "Reverses", "zh": "冲销指向"},
    "th.locator": {"en": "Locator", "zh": "定位"},
    "th.run": {"en": "run", "zh": "run"},
    "th.supersedes": {"en": "Supersedes", "zh": "替代"},
    "th.net_delta": {"en": "Net difference (minor)", "zh": "净差额(分)"},
    "th.export": {"en": "Export", "zh": "导出"},
    "th.purpose": {"en": "Purpose", "zh": "用途"},
    "th.unresolved": {"en": "Unresolved groups", "zh": "未解决组"},
    "th.files": {"en": "Files", "zh": "文件"},
    "th.id": {"en": "ID", "zh": "ID"},
    "th.type": {"en": "Type", "zh": "类型"},
    "th.object_digest": {"en": "Object digest", "zh": "对象摘要"},
    "th.action": {"en": "Action", "zh": "操作"},
    "value.unknown": {"en": "Unknown", "zh": "未知"},
    "value.not_comparable": {"en": "Not comparable", "zh": "不可比"},
    "value.none_dash": {"en": "—", "zh": "—"},
    "integrity.complete": {"en": "Complete", "zh": "完整"},
    "integrity.incomplete": {"en": "Incomplete", "zh": "不完整"},
    "integrity.incomplete_freeze": {
        "en": "Incomplete: cannot be frozen",
        "zh": "不完整：不能正式冻结",
    },
    # ---------------------------------------------------------------- 案件首页
    "home.title": {"en": "Cases", "zh": "案件首页"},
    "home.note": {
        "en": "Amounts and coverage follow the run version they belong to; this page shows no"
              " headline \u201csavings\u201d figure (§19.1).",
        "zh": "金额与覆盖以运行版本为准；本页不展示「节省金额」大字（§19.1）。",
    },
    # ---------------------------------------------------------------- 案件详情
    "case.heading": {"en": "Case: {title}", "zh": "案件：{title}"},
    "case.latest_run": {"en": "Latest run: ", "zh": "最新运行："},
    "case.run_link": {"en": "run {run_id} ({status})", "zh": "run {run_id}（{status}）"},
    "case.no_run": {"en": "No runs yet", "zh": "尚无运行"},
    "case.h2_intake": {"en": "Intake and mapping", "zh": "导入与映射"},
    "case.h2_issues": {"en": "Difference workbench", "zh": "差异工作台"},
    "case.goto_issues": {
        "en": "Open the difference workbench →",
        "zh": "进入差异工作台 →",
    },
    # ---------------------------------------------------------------- 差异工作台
    "issues.title": {"en": "Difference workbench — run {run_id}", "zh": "差异工作台 — run {run_id}"},
    "issues.no_run": {"en": "No run results yet.", "zh": "尚无运行结果。"},
    "issues.equation": {
        "en": "Bill net {billed} CNY = comparable {comparable} + non-comparable {unresolved}"
              " + explicitly excluded {excluded} (conserved)",
        "zh": "账单净额 {billed} 元 = 可比 {comparable} + 不可比 {unresolved}"
              " + 明确排除 {excluded}（守恒）",
    },
    "issues.difference_line": {
        "en": "Positive difference <b class=warn>{positive}</b> CNY, negative {negative} CNY,"
              " net {net} CNY, amount coverage {coverage}",
        "zh": "正向差额 <b class=warn>{positive}</b> 元，反向 {negative} 元，净 {net} 元，"
              "金额覆盖 {coverage}",
    },
    "issues.integrity_line": {
        "en": "Amount integrity: {state}",
        "zh": "金额完整性：{state}",
    },
    "issues.h2_amount": {
        "en": "Amount differences to verify (comparable groups, largest difference first)",
        "zh": "待核金额差异（可比组，按差额排序）",
    },
    "issues.h2_noncomparable": {
        "en": "Not comparable / missing evidence / unmatched",
        "zh": "不可比 / 缺证 / 待匹配",
    },
    "issues.h2_case": {"en": "Case-level notices", "zh": "案件级提示"},
    # ---------------------------------------------------------------- 证据复核
    "review.title": {"en": "Evidence review — {group_id}", "zh": "证据复核 — {group_id}"},
    "review.h2_bill": {"en": "Billed lines", "zh": "原账单"},
    "review.h2_trip": {"en": "Trip / evidence", "zh": "运输/凭证"},
    "review.h2_rules": {"en": "Rule and formula", "zh": "规则与公式"},
    "review.locator_cell": {"en": "{asset}, row {row}", "zh": "{asset} 第{row}行"},
    "review.no_trip": {"en": "No linked trip", "zh": "无关联运输"},
    "review.departed": {"en": "Departed: ", "zh": "出发："},
    "review.status_label": {"en": "Status: ", "zh": "状态："},
    "review.evidence_state": {"en": "Evidence state: ", "zh": "凭证状态："},
    "review.events": {"en": "Events: ", "zh": "事件："},
    "review.rule": {"en": "Rule: ", "zh": "规则："},
    "review.trace": {"en": "Trace: ", "zh": "轨迹："},
    "review.rule_not_applied": {"en": "Not applied", "zh": "未适用"},
    "review.amounts": {
        "en": "Billed net {billed} / expected {expected} / difference {delta}",
        "zh": "账单净额 {billed} / 应计 {expected} / 差额 {delta}",
    },
    "review.h2_decision": {"en": "Decision", "zh": "处理决定"},
    "review.digest": {"en": "Result digest", "zh": "结果摘要"},
    "review.current": {
        "en": "Current decision: {decision} ({status})",
        "zh": "当前决定：{decision}（{status}）",
    },
    "review.no_decision": {"en": "None", "zh": "无"},
    "review.reason_label": {"en": "Reason: ", "zh": "理由: "},
    "review.reason_default": {"en": "Admin page decision {decision}", "zh": "管理页决定 {decision}"},
    "review.note": {
        "en": "A decision never rewrites a computed value; accepting a bill keeps the original"
              " difference and the reason on record (§12.2).",
        "zh": "决定不改写计算值；接受账单会保留原始差异与理由（§12.2）。",
    },
    "decision.CONFIRMED_DIFFERENCE": {"en": "Confirm as difference", "zh": "确认为差异"},
    "decision.ACCEPTED_AS_BILLED": {
        "en": "Accept as billed (difference stays on record)",
        "zh": "接受账单原额（保留差异记录）",
    },
    "decision.NEEDS_EVIDENCE": {"en": "Needs evidence", "zh": "待补证"},
    "decision.DISPUTED": {"en": "Disputed", "zh": "争议中"},
    # ---------------------------------------------------------------- 版本与导出
    "versions.title": {"en": "Versions and exports", "zh": "版本与导出"},
    "versions.freeze": {"en": "Freeze current run", "zh": "冻结当前运行"},
    "versions.prepare_export": {"en": "Prepare export", "zh": "准备导出"},
    "versions.h2_exports": {"en": "Export records", "zh": "导出记录"},
    "versions.note": {
        "en": "An export is reconciliation material, not a payment instruction; sending it out is"
              " done by a human (§12.1 H).",
        "zh": "导出是核对材料，不是付款指令；对外发送由人执行（§12.1 H）。",
    },
    "export.purpose_local": {"en": "reconciliation material", "zh": "核对材料"},
    # ---------------------------------------------------------------- 待确认列表
    "confirmations.title": {"en": "Pending confirmations", "zh": "待确认事项"},
    "action.confirm": {"en": "Confirm", "zh": "确认"},
    "confirmations.note": {
        "en": "Confirming binds the object digest and a one-time credential; repeating it returns"
              " the original result and never creates a second approval.",
        "zh": "确认即绑定对象摘要与一次性凭证；重复确认返回原结果，不产生第二个批准。",
    },
    # ---------------------------------------------------------------- 错误页
    "error.heading": {"en": "Error", "zh": "错误"},
    "error.origin": {"en": "Origin check failed", "zh": "Origin 检查失败"},
    "error.csrf": {"en": "CSRF check failed", "zh": "CSRF 校验失败"},
    # ---------------------------------------------------------------- MCP 工具描述
    "tool.freight_create_case": {
        "en": "Create a local reconciliation case: billing entity workspace, carrier, period"
              " boundaries and amount basis. Single currency, CNY.",
        "zh": "新建本地对账案件：主体工作区、承运商、账期边界与金额口径。单一 CNY。",
    },
    "tool.freight_register_asset": {
        "en": "Register a source file (a path handle the user selected): bill / trips / rates /"
              " waiting / receipts / pod / history_trips. Returns asset_id; no authorized path"
              " escape is accepted.",
        "zh": "登记来源文件（用户已选择的路径句柄）：bill/trips/rates/waiting/receipts/pod/history_trips。"
              "返回 asset_id，不接受任意系统路径以外的授权逃逸。",
    },
    "tool.freight_inspect_asset": {
        "en": "Page through a registered asset: column names, redacted samples, row counts and"
              " parse issues.",
        "zh": "分页查看已登记资产的列名、脱敏样例、行数与解析问题。",
    },
    "tool.freight_prepare_mapping": {
        "en": "Submit field-mapping candidates (source column -> target field). Produces a draft"
              " awaiting human confirmation only; never activates it.",
        "zh": "提交字段映射候选（原列→目标字段）。仅生成待确认草稿，不激活。",
    },
    "tool.freight_prepare_rate_rules": {
        "en": "Package the imported rate table into a rule confirmation candidate (with overlap"
              " and interval checks). Prepare only; never activates it.",
        "zh": "把已导入的费率表打包为规则确认候选（含重叠/区间检查）。仅准备，不激活。",
    },
    "tool.freight_list_match_candidates": {
        "en": "List bill lines awaiting manual linking together with candidate trips"
              " (suggestions only, never auto-bound).",
        "zh": "列出待人工关联的账单行与候选运输（P3 仅建议，不自动绑定）。",
    },
    "tool.freight_prepare_match": {
        "en": "Prepare a manual link candidate between one bill line and a trip. Prepare only;"
              " never activates it.",
        "zh": "准备一条账单行与车次的人工关联候选。仅准备，不激活。",
    },
    "tool.freight_start_run": {
        "en": "Start a deterministic recalculation: freezes the input manifest and returns a"
              " job_id; poll it with freight_get_job.",
        "zh": "启动一次确定性重算：冻结输入清单并返回 job_id，用 freight_get_job 轮询。",
    },
    "tool.freight_get_job": {
        "en": "Read job status, completed/failed counts and recovery notes.",
        "zh": "查询 job 状态、完成/失败计数与恢复说明。",
    },
    "tool.freight_get_summary": {
        "en": "Read one run's amount summary and coverage (explicit denominator; an unknown"
              " amount is never turned into zero).",
        "zh": "读取一版运行的金额汇总与覆盖率（分母明确，未知不归零）。",
    },
    "tool.freight_list_issues": {
        "en": "Page through structured differences / missing-evidence / unmatched items; JSON is"
              " never truncated.",
        "zh": "分页读取结构化差异/缺证/待匹配清单，不截断 JSON。",
    },
    "tool.freight_get_evidence": {
        "en": "Read the four-column evidence locator for one issue (original bill / trip / rule"
              " evidence / calculation trace), as a redacted projection.",
        "zh": "读取单条异常的四栏证据定位（原账单/运输/规则凭证/计算轨迹），脱敏投影。",
    },
    "tool.freight_prepare_review": {
        "en": "Prepare a human review decision candidate (bound to result_digest). Prepare only;"
              " never activates it.",
        "zh": "准备一条人工复核决定候选（绑定 result_digest）。仅准备，不激活。",
    },
    "tool.freight_prepare_export": {
        "en": "Prepare export candidates (fixed projection and purpose). Nothing is sent"
              " automatically; releasing an export needs confirmation on the admin page.",
        "zh": "准备导出候选（固定投影与用途）。不自动发送；释放需管理页确认。",
    },
}
