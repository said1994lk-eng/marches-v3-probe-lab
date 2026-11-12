"""Local user-operated diagnostics for a public Moroccan procurement portal.

Runs once from the user's own Windows PC/network; never proxies, retries, logs
credentials, downloads DCE or performs any protected action. Default mode only
checks FORM_READY on approved public routes. Category mode must be explicitly
requested and makes at most one public search POST and one detail GET.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
CONNECTION_FLAG = "ENABLE_LIVE_GATE1A09"
CATEGORY_FLAG = "ENABLE_LIVE_GATE1B02"


async def execute_once(mode: str, category_ack: bool = False) -> dict:
    """Returns only the existing probes' aggregate, sanitized status fields."""
    if mode == "connection":
        from gate1a09_exact_public_search import run
        flag = CONNECTION_FLAG
    elif mode == "category" and category_ack:
        from gate1b02_probe import run
        flag = CATEGORY_FLAG
    else:
        return {
            "schema": "marches-v3-local-check/1", "status": "EXPLICIT_CONFIRMATION_REQUIRED",
            "mode": mode, "filter_attested": False,
        }
    prior = os.environ.get(flag)
    os.environ[flag] = "1"
    try:
        return await run()
    except Exception as exc:
        return {
            "schema": "marches-v3-local-check/1",
            "status": "LOCAL_RUN_EXCEPTION",
            "mode": mode,
            "error_class": type(exc).__name__[:35],
            "filter_attested": False,
        }
    finally:
        if prior is None:
            os.environ.pop(flag, None)
        else:
            os.environ[flag] = prior


def compact_safe_output(report: dict) -> dict:
    """Reject any future accidental raw HTML, URL or secrets in JSON values.

    Existing gate reports use enums/booleans/counts, not raw user text. This
    check is intentionally conservative: it will drop an entire value if
    upstream code starts exporting raw page content later on.
    """
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()
                    if isinstance(k, str) and k.isidentifier() and len(k) <= 64}
        if isinstance(value, (list, tuple)):
            return [clean(v) for v in value[:25]]
        if isinstance(value, str):
            if len(value) > 180 or any(c in value for c in ("<", ">", "\n", "\r", "://", "@")):
                return "REDACTED"
            return value
        if value is None or type(value) in (int, bool, float):
            return value
        return None
    return clean(report)


def save_report(report: dict, mode: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_UTC")
    target = output_dir / f"local_{mode}_{timestamp}.json"
    target.write_text(
        json.dumps(compact_safe_output(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Local, public, bounded one-shot portal check")
    parser.add_argument("--mode", choices=("connection", "category"), default="connection")
    parser.add_argument("--ack-one-post-one-detail", action="store_true",
                        help="Required for category mode; no login and max one post/detail")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "local-reports")
    args = parser.parse_args()
    if args.mode == "category" and not args.ack_one_post_one_detail:
        print("CATEGORY_MODE_NEEDS_EXPLICIT_FLAG")
        return 2
    report = compact_safe_output(asyncio.run(
        execute_once(args.mode, args.ack_one_post_one_detail)
    ))
    target = save_report(report, args.mode, args.output_dir)
    print("=== Marches Intelligence V3 - local connection diagnosis ===")
    print("Mode:", args.mode)
    print("Status:", report.get("status", "UNKNOWN"))
    navigation = report.get("navigation")
    if isinstance(navigation, dict):
        print("Form ready:", navigation.get("form_ready"))
        print("Reason:", navigation.get("reason_code"))
        for observation in navigation.get("observations", ()):
            if isinstance(observation, dict):
                print("Route:", observation.get("route_id"),
                      "HTTP:", observation.get("http_status"),
                      "State:", observation.get("state"))
    if args.mode == "category":
        print("Search clicks:", report.get("search_clicks", 0))
        print("Detail GET attempts:", report.get("detail_get_attempts", 0))
        print("Result category attested:", report.get("source_labelled_sample_confirmed", False))
        detail = report.get("direct_spot_check")
        if isinstance(detail, dict):
            print("Single-record category proof:", detail.get("status", "UNCONFIRMED"))
    print("Report:", str(target))
    accepted = (
        (args.mode == "connection" and report.get("status") == "FORM_READY_CONFIRMED_ONCE")
        or (args.mode == "category" and report.get("status")
            in ("DIRECT_SPOT_CHECK_ONLY", "SAMPLED_CONFIRMED"))
    )
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
