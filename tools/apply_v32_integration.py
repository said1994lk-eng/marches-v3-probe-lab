"""Produce a diagnostic-only preview of V3.2 without altering the original.

Usage (from repository root):
    python tools/apply_v32_integration.py src/reliability_v32.py \
        src/reliability_v32_gate1a_preview.py

The preview does NOT change navigation, retry, filter or exit decisions.
Do not run the preview against the live site without a separate test plan.
"""
from __future__ import annotations

import argparse
from pathlib import Path

IMPORT_ANCHOR = (
    "from full_coverage import SEARCH, PAGE_SIZE, NEXT, PREV, official_count, "
    "get_cards, change_page, wait_card_count\n"
)
HELPER_ANCHOR = "async def soft_count(page):\n"
TIMEOUT_ANCHOR = (
    '                    if navigation_index == len(route_urls):\n'
    '                        raise ValueError("BOTH_OFFICIAL_ROUTES_DOMCONTENTLOADED_TIMEOUT")\n'
)
SUCCESS_ANCHOR = (
    '                health["dom_after_navigation_" + str(navigation_index)] = await safe_dom_snapshot(page)\n'
    '                if await category.count():\n'
)
HELPER = '''async def safe_page_classification(page, *, http_status=None, navigation_timed_out=False):
    """Observe page state for diagnostics; never modify the V3.2 control flow."""
    try:
        return await classify_playwright_page(
            page, http_status=http_status, navigation_timed_out=navigation_timed_out
        )
    except Exception:
        return {
            "state": "UNKNOWN_LAYOUT",
            "reason_code": "CLASSIFIER_CAPTURE_UNAVAILABLE",
            "next_action": "STOP_AND_REVIEW_STRUCTURE",
            "confidence": "LOW",
            "navigation_timed_out": navigation_timed_out,
        }


'''


def patch_source(source: str) -> str:
    """Fail closed if V3.2 changed or the preview was already applied."""
    if "from page_state import classify_playwright_page" in source:
        raise ValueError("ALREADY_PATCHED")
    for anchor in (IMPORT_ANCHOR, HELPER_ANCHOR, TIMEOUT_ANCHOR, SUCCESS_ANCHOR):
        if source.count(anchor) != 1:
            raise ValueError("UNEXPECTED_SOURCE_STRUCTURE: " + anchor[:64])
    source = source.replace(
        IMPORT_ANCHOR,
        IMPORT_ANCHOR + "from page_state import classify_playwright_page\n",
        1,
    )
    source = source.replace(HELPER_ANCHOR, HELPER + HELPER_ANCHOR, 1)
    source = source.replace(
        TIMEOUT_ANCHOR,
        '''                    health["page_classification_" + str(navigation_index)] = (
                        await safe_page_classification(page, navigation_timed_out=True)
                    )
''' + TIMEOUT_ANCHOR,
        1,
    )
    source = source.replace(
        SUCCESS_ANCHOR,
        '''                health["dom_after_navigation_" + str(navigation_index)] = await safe_dom_snapshot(page)
                health["page_classification_" + str(navigation_index)] = (
                    await safe_page_classification(page, http_status=r.status if r else None)
                )
                if await category.count():
''',
        1,
    )
    return source


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a separate diagnostic-only V3.2 integration preview"
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("Output must differ from input: original is immutable")
    updated = patch_source(args.source.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(updated, encoding="utf-8")
    print(f"Preview written to {args.output}; original unchanged")


if __name__ == "__main__":
    main()
