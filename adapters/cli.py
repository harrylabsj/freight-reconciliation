"""开发/回归 CLI（§18.2）：与 MCP 连接器共用同一 Core 与权限检查。

仅为开发与回归入口；生产交互走 WorkBuddy 专家（MCP）+ 本地管理页。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from freight_core.service import ReconciliationService  # noqa: E402

DEFAULT_ROOT = os.environ.get(
    "FREIGHT_RECON_ROOT",
    str(Path.home() / ".local" / "share" / "freight-reconciliation"))


def _svc(args) -> ReconciliationService:
    return ReconciliationService(args.root)


def cmd_create_case(a):
    svc = _svc(a)
    case = svc.freight_create_case(a.title, a.carrier, a.period_from, a.period_to,
                                   history_coverage=(a.hist_from, a.hist_to)
                                   if a.hist_from else None)
    print(json.dumps(case, ensure_ascii=False, indent=2))
    svc.close()


def cmd_confirm_mapping(a):
    svc = _svc(a)
    header = __import__("csv").reader(open(a.file, encoding="utf-8-sig")).__next__()
    doc = svc.freight_prepare_mapping(a.case, a.kind, [h.strip() for h in header])
    out = svc.admin_confirm(doc["confirmation_id"])
    print(json.dumps(out, ensure_ascii=False))
    svc.close()


def cmd_register(a):
    svc = _svc(a)
    asset = svc.freight_register_asset(a.case, a.file, a.kind,
                                       declared_total_minor=a.declared_total)
    print(json.dumps({k: v for k, v in asset.items() if k != "rows_sample"},
                     ensure_ascii=False, indent=2))
    svc.close()


def cmd_prepare_rules(a):
    svc = _svc(a)
    out = svc.freight_prepare_rate_rules(a.case)
    result = svc.admin_confirm(out["confirmation_id"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    svc.close()


def cmd_run(a):
    svc = _svc(a)
    job = svc.freight_start_run(a.case)
    for _ in range(600):
        state = svc.freight_get_job(job["job_id"])
        if state["status"] in ("SUCCEEDED", "PARTIAL", "FAILED"):
            break
        time.sleep(0.1)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    svc.close()


def cmd_summary(a):
    svc = _svc(a)
    print(json.dumps(svc.freight_get_summary(a.run), ensure_ascii=False, indent=2))
    svc.close()


def cmd_issues(a):
    svc = _svc(a)
    out = svc.freight_list_issues(a.run, code=a.code, limit=a.limit)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    svc.close()


def cmd_freeze(a):
    svc = _svc(a)
    print(json.dumps(svc.admin_confirm_freeze(a.case, a.run), ensure_ascii=False, indent=2))
    svc.close()


def cmd_export(a):
    svc = _svc(a)
    out = svc.freight_prepare_export(a.case, a.run, a.purpose)
    if a.release:
        released = svc.admin_confirm(out["confirmation_id"])
        print(json.dumps(released, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    svc.close()


def main() -> None:
    p = argparse.ArgumentParser(prog="freight-cli", description="海纳·运费对账 开发CLI")
    p.add_argument("--root", default=DEFAULT_ROOT, help="工作区根目录")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("create-case")
    s.add_argument("--title", required=True)
    s.add_argument("--carrier", required=True)
    s.add_argument("--period-from", dest="period_from", required=True)
    s.add_argument("--period-to", dest="period_to", required=True)
    s.add_argument("--hist-from", dest="hist_from", default=None)
    s.add_argument("--hist-to", dest="hist_to", default=None)
    s.set_defaults(fn=cmd_create_case)

    s = sub.add_parser("confirm-mapping")
    s.add_argument("--case", required=True)
    s.add_argument("--kind", required=True)
    s.add_argument("--file", required=True, help="以该文件实际表头生成并确认映射")
    s.set_defaults(fn=cmd_confirm_mapping)

    s = sub.add_parser("register")
    s.add_argument("--case", required=True)
    s.add_argument("--kind", required=True)
    s.add_argument("--file", required=True)
    s.add_argument("--declared-total", dest="declared_total", type=int, default=None,
                   help="账单声明合计（分），用于控制总数")
    s.set_defaults(fn=cmd_register)

    s = sub.add_parser("prepare-rules")
    s.add_argument("--case", required=True)
    s.set_defaults(fn=cmd_prepare_rules)

    s = sub.add_parser("run")
    s.add_argument("--case", required=True)
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("summary")
    s.add_argument("--run", required=True)
    s.set_defaults(fn=cmd_summary)

    s = sub.add_parser("issues")
    s.add_argument("--run", required=True)
    s.add_argument("--code", default=None)
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(fn=cmd_issues)

    s = sub.add_parser("freeze")
    s.add_argument("--case", required=True)
    s.add_argument("--run", required=True)
    s.set_defaults(fn=cmd_freeze)

    s = sub.add_parser("export")
    s.add_argument("--case", required=True)
    s.add_argument("--run", required=True)
    s.add_argument("--purpose", default="与承运商核对")
    s.add_argument("--release", action="store_true")
    s.set_defaults(fn=cmd_export)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
