"""本地管理页（§19.1 五页面 + §17.1 确认路由）。

- 仅监听 127.0.0.1；独立会话 cookie + CSRF token + Origin/Host 检查。
- GET 无副作用；POST 才能确认；一次性确认凭证不进模型上下文。
- prepare/confirm 分离：这里是人类确认的唯一入口；MCP 模型层不可达。
- 所有模型/账单可控的插值一律经 ``e()``（html.escape）转义：案件标题、资产名、
  条款、issue 文案、决定理由等，绝不裸插进 HTML——否则模型可注入 <script> 读走
  同页 CSRF token 并自行 POST /confirm，等于把「必须人类确认」交还给模型。
- 界面文案英文件默认、中文为备用（``freight_core.i18n``，按 Accept-Language /
  FREIGHT_LANG / LANG 解析）；确认依据与计算值不受语言影响。

页面：
  /                          案件首页（账期/主体/承运商/覆盖/版本，不给"节省金额"大字）
  /cases/{id}                案件详情（导入与映射页）
  /cases/{id}/issues         差异工作台（分区展示，不可比金额不混入差额榜）
  /cases/{id}/review/{run}/{group}  证据复核页（四栏：原账单/运输凭证/规则公式/决定）
  /cases/{id}/versions       版本与导出页（新旧差异、未解决项、导出确认）
  /admin/confirmations       待确认列表
  POST /admin/confirmations/{id}/confirm   确认路由（CSRF+会话+一次性凭证）
  POST /admin/cases/{id}/freeze            冻结确认
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import uuid
from html import escape as _escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

REPO_ROOT = Path(__file__).resolve().parents[1]
# 开发树布局才把 src/ 插进 sys.path；pip/uvx 安装后 freight_core 已可直接导入。
if (REPO_ROOT / "src" / "freight_core").is_dir():
    sys.path.insert(0, str(REPO_ROOT / "src"))

from freight_core.i18n import resolve_lang, t  # noqa: E402
from freight_core.service import ReconciliationService  # noqa: E402
from freight_core.errors import FreightError  # noqa: E402

DEFAULT_ROOT = os.environ.get(
    "FREIGHT_RECON_ROOT",
    str(Path.home() / ".local" / "share" / "freight-reconciliation"))

# 只有回环地址算同源（本服务仅 bind 127.0.0.1）。
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

_PAGE = """<!doctype html><html lang="{lang}"><meta charset=utf-8>
<title>{title}</title>
<style>
body{{font-family:-apple-system,sans-serif;margin:2em;color:#222}}
table{{border-collapse:collapse;margin:1em 0}}td,th{{border:1px solid #ccc;padding:4px 10px;font-size:14px}}
h1{{font-size:20px}}h2{{font-size:16px}} .warn{{color:#b00}} .ok{{color:#070}}
form{{display:inline}} button{{padding:4px 12px}} nav a{{margin-right:1em}}
.badge{{background:#eee;border-radius:4px;padding:2px 6px;font-size:12px}}
</style>
<nav><a href="/">{nav_home}</a><a href="/admin/confirmations">{nav_pending}</a></nav>
{body}"""

_FORM = """<form method=post action="{action}"><input type=hidden name=csrf value="{csrf}">
<button {disabled}>{label}</button></form>"""


def e(value) -> str:
    """HTML 转义任意模型/文件来源的值（quote=True 同时覆盖属性上下文）。"""
    if value is None:
        return ""
    return _escape(str(value), quote=True)


def te(key: str, lang: str, **fields) -> str:
    """取文案并转义：用于自身不含标记的标签/取值文本节点。"""
    return e(t(key, lang, **fields))


def _heads(keys: tuple[str, ...], lang: str) -> str:
    return "".join(f"<th>{te(k, lang)}</th>" for k in keys)


class AdminState:
    def __init__(self, root: str):
        self.service = ReconciliationService(root)
        self.sessions: dict[str, str] = {}  # cookie -> csrf
        self.password = os.environ.get("FREIGHT_ADMIN_TOKEN")
        if not self.password:
            raise RuntimeError("FREIGHT_ADMIN_TOKEN is required")


STATE: AdminState | None = None


def _rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 安静日志；不落整表/隐私（§20.2）
        sys.stderr.write("admin: " + fmt % args + "\n")

    # ------------------------------------------------------------- 基础
    def _lang(self) -> str:
        """每请求解析界面语言：FREIGHT_LANG → Accept-Language → LANG → 英文。"""
        return resolve_lang(self.headers.get("Accept-Language"))

    def _session(self):
        cookies = self.headers.get("Cookie", "")
        token = None
        for part in cookies.split(";"):
            if part.strip().startswith("fsession="):
                token = part.split("=", 1)[1].strip()
        return token if token in STATE.sessions else None

    def _check_origin(self) -> bool:
        """同源校验按**解析后的 host** 精确比对，不做后缀匹配。

        ``origin.endswith(host)`` 会放过 ``http://evil-127.0.0.1.example``：浏览器视其为
        跨源，但后缀匹配判定通过，于是外部页面能带着会话发起写请求。这里改为解析 Origin
        的 scheme/host/port 与 Host 头双重比对，端口必须等于本服务实际监听端口。
        """
        origin = self.headers.get("Origin")
        if origin is None:
            return True  # 同源表单（非浏览器客户端也走会话+CSRF）
        parsed = urlparse(origin)
        if parsed.scheme not in ("http", "https"):
            return False
        if parsed.hostname not in LOOPBACK_HOSTS:
            return False
        bound_port = getattr(self.server, "server_port", None)
        if parsed.port is not None and bound_port is not None and parsed.port != bound_port:
            return False
        host_header = (self.headers.get("Host") or "").strip()
        if host_header.startswith("["):  # IPv6 字面量 [::1]:8765
            host_name = host_header.partition("]")[0][1:]
        else:
            host_name = host_header.rsplit(":", 1)[0]
        return host_name.strip().lower() in LOOPBACK_HOSTS

    def _csrf_ok(self, form: dict) -> bool:
        session = self._session()
        return session is not None and form.get("csrf") == STATE.sessions[session]

    def _html(self, body: str, status: int = 200, headers: dict | None = None) -> None:
        lang = self._lang()
        data = _PAGE.format(lang=e(lang), title=te("page.title", lang),
                            nav_home=te("nav.home", lang),
                            nav_pending=te("nav.pending", lang), body=body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Frame-Options", "DENY")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location: str, headers: dict | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _form(self, action: str, label: str, disabled: bool = False) -> str:
        session = self._session()
        csrf = STATE.sessions.get(session, "")
        dis = "disabled" if disabled else ""
        return _FORM.format(action=e(action), csrf=e(csrf), label=e(label), disabled=dis)

    # ------------------------------------------------------------- GET
    def do_GET(self):
        if self._session() is None:
            return self._login_page()
        path = urlparse(self.path).path
        try:
            if path == "/":
                return self._page_home()
            m = path.split("/")
            if path == "/admin/confirmations":
                return self._page_confirmations()
            if len(m) == 3 and m[1] == "cases":
                return self._page_case(m[2])
            if len(m) == 4 and m[3] == "issues":
                return self._page_issues(m[2])
            if len(m) == 4 and m[3] == "versions":
                return self._page_versions(m[2])
            if len(m) == 6 and m[3] == "review":
                return self._page_review(m[2], m[4], m[5])
            return self._html("<h1>404</h1>", 404)
        except FreightError as exc:
            lang = self._lang()
            return self._html(f'<h1 class=warn>{te("error.heading", lang)}</h1>'
                              f'<p class=warn>{e(exc.message)}</p>', 400)

    def _login_page(self, error: str = "") -> None:
        lang = self._lang()
        self._html(f'<h1>{te("login.title", lang)}</h1>\n'
                   '<form method=post action="/admin/login">'
                   f'{te("login.token_label", lang)}: <input type=password name=token>\n'
                   f'<input type=submit value="{te("login.submit", lang)}"></form>'
                   f'<p class=warn>{e(error)}</p>\n'
                   f'<p>{te("login.note", lang)}</p>')

    def _page_home(self) -> None:
        lang = self._lang()
        na = t("value.none_dash", lang)
        cases = _rows_to_dicts(STATE.service.db.conn.execute(
            "SELECT * FROM cases ORDER BY created_at DESC").fetchall())
        rows = "".join(
            f'<tr><td><a href="/cases/{e(c["id"])}">{e(c["title"])}</a></td>'
            f'<td>{e(c["carrier_id"])}</td><td>{e(c["period_from"])}~{e(c["period_to"])}</td>'
            f'<td><span class=badge>{e(c["status"])}</span></td>'
            f'<td>{te("th.revision", lang)} {e(c["case_revision"])}</td>'
            f'<td>{e(c["currency"])}/{e(c["amount_basis"])}</td></tr>' for c in cases)
        self._html(f'<h1>{te("home.title", lang)}</h1><table><tr>'
                   + _heads(("th.case", "th.carrier", "th.period", "th.status",
                             "th.revision", "th.currency_basis"), lang)
                   + f'</tr>{rows or "<tr><td colspan=6>" + e(na) + "</td></tr>"}</table>'
                   + f'<p>{te("home.note", lang)}</p>')

    def _page_case(self, case_id: str) -> None:
        lang = self._lang()
        svc = STATE.service
        case = svc.get_case(case_id)
        assets = _rows_to_dicts(svc.db.conn.execute(
            "SELECT * FROM assets WHERE case_id=?", (case_id,)).fetchall())
        rows = "".join(
            f'<tr><td>{e(a["id"])}</td><td>{e(a["kind"])}</td><td>{e(a["original_name"])}</td>'
            f'<td>{e(a["detail_rows"])}</td><td>{e(a["parse_error_rows"])}</td>'
            f'<td>{t("integrity.complete", lang) if a["amount_complete"] else "<b class=warn>" + te("integrity.incomplete", lang) + "</b>"}</td></tr>'
            for a in assets)
        latest = svc.db.conn.execute(
            "SELECT run_id, status FROM runs WHERE case_id=? ORDER BY created_at DESC"
            " LIMIT 1", (case_id,)).fetchone()
        run_link = (f'<a href="/cases/{e(case_id)}/versions">'
                    + te("case.run_link", lang, run_id=latest["run_id"], status=latest["status"])
                    + "</a>") if latest else te("case.no_run", lang)
        self._html(f'<h1>{te("case.heading", lang, title=case["title"])}</h1>\n'
                   f'<p>{e(case["workspace_id"])} / {e(case["carrier_id"])} / '
                   f'{e(case["period_from"])} ~ {e(case["period_to"])} / '
                   f'{e(case["currency"])} {e(case["amount_basis"])} / '
                   f'<span class=badge>{e(case["status"])}</span></p>\n'
                   f'<p>{te("case.latest_run", lang)}{run_link}</p>\n'
                   f'<h2>{te("case.h2_intake", lang)}</h2>\n'
                   "<table><tr>"
                   + _heads(("th.asset", "th.kind", "th.filename", "th.detail_rows",
                             "th.failed_rows", "th.amount_integrity"), lang)
                   + f'</tr>{rows}</table>\n'
                   f'<h2>{te("case.h2_issues", lang)}</h2>'
                   f'<p><a href="/cases/{e(case_id)}/issues">'
                   f'{te("case.goto_issues", lang)}</a></p>')

    def _page_issues(self, case_id: str) -> None:
        lang = self._lang()
        svc = STATE.service
        run = svc.db.conn.execute(
            "SELECT * FROM runs WHERE case_id=? ORDER BY created_at DESC LIMIT 1",
            (case_id,)).fetchone()
        if run is None:
            return self._html(f'<h1>{te("issues.title", lang, run_id="—")}</h1>'
                              f'<p>{te("issues.no_run", lang)}</p>')
        summary = json.loads(run["summary"]) if run["summary"] else {}
        groups = _rows_to_dicts(svc.db.conn.execute(
            "SELECT g.*, r.comparison_status, r.evidence_status, r.delta_minor, r.issues,"
            " r.expected_minor, r.result_digest FROM charge_groups g JOIN results r"
            " ON r.run_id=g.run_id AND r.group_id=g.group_id WHERE g.run_id=?"
            " ORDER BY g.group_id", (run["run_id"],)).fetchall())
        unknown = t("value.unknown", lang)
        not_comparable = t("value.not_comparable", lang)
        amt_rows = "".join(
            f'<tr><td><a href="/cases/{e(case_id)}/review/{e(run["run_id"])}/{e(g["group_id"])}">'
            f'{e(g["group_id"])}</a></td><td>{e(g["trip_id"] or "—")}</td>'
            f'<td>{e(g["charge_code"])}</td><td>{e(g["billed_minor"])}</td>'
            f'<td>{e(g["expected_minor"]) if g["expected_minor"] is not None else e(unknown)}</td>'
            f'<td class={"warn" if (g["delta_minor"] or 0) > 0 else ""}>'
            f'{e(g["delta_minor"]) if g["delta_minor"] is not None else e(not_comparable)}</td>'
            f'<td>{e(g["issues"])}</td></tr>'
            for g in sorted(groups, key=lambda g: -(g["delta_minor"] or 0))
            if g["delta_minor"] is not None and g["delta_minor"] != 0)
        nc_rows = "".join(
            f'<tr><td><a href="/cases/{e(case_id)}/review/{e(run["run_id"])}/{e(g["group_id"])}">'
            f'{e(g["group_id"])}</a></td><td>{e(g["match_state"])}</td><td>{e(g["pod_state"])}</td>'
            f'<td>{e(g["billed_minor"])}</td><td>{e(g["issues"])}</td></tr>'
            for g in groups if g["comparison_status"] != "COMPARABLE")
        case_issues = _rows_to_dicts(svc.db.conn.execute(
            "SELECT * FROM issues WHERE run_id=? AND group_id='__case__'",
            (run["run_id"],)).fetchall())
        ci_rows = "".join(f'<tr><td>{e(i["code"])}</td><td>{e(i["message"])}</td></tr>'
                          for i in case_issues)
        cov_den = summary.get("abs_total_billed_minor") or 0
        cov = (f"{summary.get('abs_comparable_billed_minor', 0) / cov_den:.2%}"
               if cov_den else unknown)
        equation = t("issues.equation", lang,
                     billed=f"{summary.get('source_signed_total_minor', 0) / 100:.2f}",
                     comparable=f"{summary.get('comparable_billed_minor', 0) / 100:.2f}",
                     unresolved=f"{summary.get('unresolved_billed_minor', 0) / 100:.2f}",
                     excluded=f"{summary.get('out_of_scope_billed_minor', 0) / 100:.2f}")
        difference = t("issues.difference_line", lang,
                       positive=f"{summary.get('positive_difference_minor', 0) / 100:.2f}",
                       negative=f"{summary.get('negative_difference_minor', 0) / 100:.2f}",
                       net=f"{summary.get('net_difference_minor', 0) / 100:.2f}",
                       coverage=e(cov))
        integrity = ('<span class=ok>' + te("integrity.complete", lang) + "</span>"
                     if run["amount_complete"] else
                     '<b class=warn>' + te("integrity.incomplete_freeze", lang) + "</b>")
        self._html(f'<h1>{te("issues.title", lang, run_id=run["run_id"])}</h1>\n'
                   f'<p>{e(equation)}\n{e(difference)}</p>\n'
                   f'<p>{t("issues.integrity_line", lang, state=integrity)}</p>\n'
                   f'<h2>{te("issues.h2_amount", lang)}</h2>\n'
                   "<table><tr>"
                   + _heads(("th.group", "th.trip", "th.charge", "th.billed_minor",
                             "th.expected_minor", "th.delta_minor", "th.issues"), lang)
                   + f'</tr>{amt_rows}</table>\n'
                   f'<h2>{te("issues.h2_noncomparable", lang)}</h2>\n'
                   "<table><tr>"
                   + _heads(("th.group", "th.match", "th.evidence", "th.billed_minor",
                             "th.issues"), lang)
                   + f'</tr>{nc_rows}</table>\n'
                   f'<h2>{te("issues.h2_case", lang)}</h2><table><tr>'
                   + _heads(("th.code", "th.message"), lang)
                   + f'</tr>{ci_rows}</table>')

    def _page_review(self, case_id: str, run_id: str, group_id: str) -> None:
        lang = self._lang()
        svc = STATE.service
        ev = svc.freight_get_evidence(run_id, group_id)
        result = ev["result"] or {}
        unknown = t("value.unknown", lang)
        not_comparable = t("value.not_comparable", lang)
        lines = "".join(
            f'<tr><td>{e(l["line_id"])}</td><td>{e(l["amount_minor"])}</td>'
            f'<td>{e(l["reversal_of"] or "")}</td>'
            f'<td>{te("review.locator_cell", lang, asset=l["locator"]["asset_id"], row=l["locator"]["row"])}</td></tr>'
            for l in ev["bill_lines"])
        trip = ev["trip"] or {}
        decision = ev.get("decision") or {}
        csrf = e(STATE.sessions.get(self._session(), ""))
        decision_forms = ""
        for code, key in [("CONFIRMED_DIFFERENCE", "decision.CONFIRMED_DIFFERENCE"),
                          ("ACCEPTED_AS_BILLED", "decision.ACCEPTED_AS_BILLED"),
                          ("NEEDS_EVIDENCE", "decision.NEEDS_EVIDENCE"),
                          ("DISPUTED", "decision.DISPUTED")]:
            decision_forms += (f'<form method=post action="/admin/confirm-review/'
                               f'{e(case_id)}/{e(run_id)}/{e(group_id)}">'
                               f'<input type=hidden name=csrf value="{csrf}">'
                               f'<input type=hidden name=decision value="{e(code)}">'
                               f'{te("review.reason_label", lang)}<input name=reason size=40> '
                               f'<button>{te(key, lang)}</button></form>')
        expected = (e(result.get("expected_minor"))
                    if result.get("expected_minor") is not None else e(unknown))
        delta = (e(result.get("delta_minor"))
                 if result.get("delta_minor") is not None else e(not_comparable))
        trace = "<br>".join(e(line) for line in (result.get("trace") or []))
        self._html(f'<h1>{te("review.title", lang, group_id=group_id)}</h1>\n'
                   "<table style=width:100%><tr>\n"
                   f'<td style=vertical-align:top width=33%><h2>{te("review.h2_bill", lang)}</h2>'
                   "<table><tr>"
                   + _heads(("th.line", "th.amount_minor", "th.reversal_of", "th.locator"), lang)
                   + f'</tr>{lines}</table></td>\n'
                   f'<td style=vertical-align:top width=33%><h2>{te("review.h2_trip", lang)}</h2>\n'
                   f'<p>{e(trip.get("trip_id") or t("review.no_trip", lang))} '
                   f'{e(trip.get("route_id", ""))} {e(trip.get("vehicle_class", ""))}<br>\n'
                   f'{te("review.departed", lang)}{e(trip.get("departed_at") or "—")}　'
                   f'{te("review.status_label", lang)}{e(trip.get("execution_status") or "—")}</p>\n'
                   f'<p>{te("review.evidence_state", lang)}{e(ev["group"]["pod_state"])}；'
                   f'{te("review.events", lang)}'
                   f'{e(json.dumps(ev["group"]["event"], ensure_ascii=False))}</p></td>\n'
                   f'<td style=vertical-align:top width=33%><h2>{te("review.h2_rules", lang)}</h2>\n'
                   f'<p>{te("review.rule", lang)}'
                   f'{e(result.get("rule_ref") or t("review.rule_not_applied", lang))}<br>'
                   f'{te("review.trace", lang)}{trace}</p>\n'
                   f'<p>{t("review.amounts", lang, billed=e(result.get("billed_minor")), expected=expected, delta=delta)}</p></td></tr></table>\n'
                   f'<h2>{te("review.h2_decision", lang)}</h2>\n'
                   f'<p>{te("review.digest", lang)} '
                   f'<code>{e((result.get("result_digest") or "")[:24])}…</code>\n'
                   f'　{t("review.current", lang, decision=e(decision.get("decision") or t("review.no_decision", lang)), status=e(decision.get("status") or "—"))}</p>\n'
                   f'{decision_forms}\n'
                   f'<p class=warn>{te("review.note", lang)}</p>')

    def _page_versions(self, case_id: str) -> None:
        lang = self._lang()
        svc = STATE.service
        runs = _rows_to_dicts(svc.db.conn.execute(
            "SELECT * FROM runs WHERE case_id=? ORDER BY created_at", (case_id,)).fetchall())
        rows = "".join(
            f'<tr><td>{e(r["run_id"])}</td><td>{e(r["status"])}</td>'
            f'<td>{e(r["supersedes_run_id"] or "—")}</td>'
            f'<td>{e(json.loads(r["summary"]).get("net_difference_minor")) if r["summary"] else "—"}</td>'
            f'<td>{t("integrity.complete", lang) if r["amount_complete"] else "<b class=warn>" + te("integrity.incomplete", lang) + "</b>"}</td></tr>'
            for r in runs)
        latest = runs[-1] if runs else None
        freeze = ""
        export = ""
        if latest is not None:
            case = svc.get_case(case_id)
            can_freeze = latest["amount_complete"] == 1 and case["status"] != "FROZEN"
            freeze = self._form(f"/admin/cases/{case_id}/freeze?run={latest['run_id']}",
                                t("versions.freeze", lang), disabled=not can_freeze)
            export = self._form(f"/admin/cases/{case_id}/prepare-export?run={latest['run_id']}",
                               t("versions.prepare_export", lang))
        exports = _rows_to_dicts(svc.db.conn.execute(
            "SELECT * FROM exports WHERE case_id=? ORDER BY created_at DESC",
            (case_id,)).fetchall())
        ex_rows = ""
        for x in exports:
            links = " ".join(
                f'<a href="/download/{e(x["export_id"])}/{e(a["name"])}">{e(a["name"])}</a>'
                for a in json.loads(x["artifacts"]))
            ex_rows += (f'<tr><td>{e(x["export_id"])}</td><td>{e(x["status"])}</td>'
                        f'<td>{e(x["purpose"])}</td><td>{e(x["unresolved_group_count"])}</td>'
                        f'<td>{links}</td></tr>')
        self._html(f'<h1>{te("versions.title", lang)}</h1>\n'
                   "<table><tr>"
                   + _heads(("th.run", "th.status", "th.supersedes", "th.net_delta",
                             "th.amount_integrity"), lang)
                   + f'</tr>{rows}</table>\n'
                   f'<p>{freeze} {export}</p>\n'
                   f'<h2>{te("versions.h2_exports", lang)}</h2><table><tr>'
                   + _heads(("th.export", "th.status", "th.purpose", "th.unresolved",
                             "th.files"), lang)
                   + f'</tr>{ex_rows}</table>\n'
                   f'<p class=warn>{te("versions.note", lang)}</p>')

    def _page_confirmations(self) -> None:
        lang = self._lang()
        reqs = _rows_to_dicts(STATE.service.db.conn.execute(
            "SELECT * FROM confirmation_requests WHERE status='PENDING'"
            " ORDER BY created_at DESC").fetchall())
        rows = ""
        for r in reqs:
            action = f"/admin/confirmations/{r['id']}/confirm"
            rows += (f'<tr><td>{e(r["id"])}</td><td>{e(r["kind"])}</td><td>{e(r["case_id"])}</td>'
                     f'<td><code>{e((r["object_digest"] or "")[:16])}…</code></td>'
                     f'<td>{self._form(action, label=t("action.confirm", lang))}</td></tr>')
        self._html(f'<h1>{te("confirmations.title", lang)}</h1>\n'
                   "<table><tr>"
                   + _heads(("th.id", "th.type", "th.case", "th.object_digest", "th.action"), lang)
                   + f'</tr>{rows}</table>\n'
                   f'<p>{te("confirmations.note", lang)}</p>')

    # ------------------------------------------------------------- POST
    def do_POST(self):
        lang = self._lang()
        if not self._check_origin():
            return self._html(f'<h1 class=warn>{te("error.origin", lang)}</h1>', 403)
        length = int(self.headers.get("Content-Length") or 0)
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
        path = urlparse(self.path).path
        if path == "/admin/login":
            if form.get("token") == STATE.password:
                session = secrets.token_urlsafe(24)
                STATE.sessions[session] = secrets.token_urlsafe(24)
                return self._redirect("/", {"Set-Cookie": f"fsession={session}; HttpOnly; SameSite=Strict; Path=/"})
            return self._login_page(t("login.error", lang))
        if self._session() is None:
            return self._redirect("/")
        if not self._csrf_ok(form):
            return self._html(f'<h1 class=warn>{te("error.csrf", lang)}</h1>', 403)
        m = path.split("/")
        try:
            if len(m) == 5 and m[1] == "admin" and m[2] == "confirmations" and m[4] == "confirm":
                STATE.service.admin_confirm(m[3])
                return self._redirect("/admin/confirmations")
            if len(m) == 5 and m[1] == "admin" and m[2] == "cases" and m[4] == "freeze":
                qs = parse_qs(urlparse(self.path).query)
                STATE.service.admin_confirm_freeze(m[3], qs["run"][0])
                return self._redirect(f"/cases/{m[3]}/versions")
            if len(m) == 5 and m[1] == "admin" and m[2] == "cases" and m[4] == "prepare-export":
                qs = parse_qs(urlparse(self.path).query)
                STATE.service.freight_prepare_export(m[3], qs["run"][0],
                                                     t("export.purpose_local", lang))
                return self._redirect("/admin/confirmations")
            if len(m) == 6 and m[1] == "admin" and m[2] == "confirm-review":
                _, _, _, case_id, run_id, group_id = m
                svc = STATE.service
                decision = form.get("decision")
                reason = form.get("reason") or t("review.reason_default", lang,
                                                 decision=decision)
                prep = svc.freight_prepare_review(case_id, run_id, group_id, decision, reason)
                svc.admin_confirm(prep["confirmation_id"])
                return self._redirect(f"/cases/{case_id}/review/{run_id}/{group_id}")
            return self._html("<h1>404</h1>", 404)
        except FreightError as exc:
            return self._html(f'<h1 class=warn>{te("error.heading", lang)}</h1>'
                              f'<p class=warn>{e(exc.message)}</p>', 400)


def main() -> None:
    global STATE
    port = int(os.environ.get("FREIGHT_ADMIN_PORT", "8765"))
    STATE = AdminState(DEFAULT_ROOT)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"admin page: http://127.0.0.1:{port}/  (local only)")
    server.serve_forever()


if __name__ == "__main__":
    main()
