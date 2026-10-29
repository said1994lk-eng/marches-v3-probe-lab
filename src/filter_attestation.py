"""Gate 1A-02: evidence-gated Fournitures filter attestation.

Selecting a dropdown option, a postback, HTTP 200, or fewer results cannot by
itself establish a server-side category filter. Proof must come from actual
source-labelled result categories or detail pages. No live requests here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Sequence
import unicodedata


class Proof(str, Enum):
    CONFIRMED = "CONFIRMED"
    UNCONFIRMED = "UNCONFIRMED"
    CONTRADICTED = "CONTRADICTED"


def normalized_category(value: object) -> str:
    if not isinstance(value, str):
        return ""
    plain = unicodedata.normalize("NFKD", value)
    return " ".join("".join(c for c in plain if not unicodedata.combining(c)).casefold().split())


@dataclass(frozen=True)
class FilterEvidence:
    selected: bool
    retained_after_search: bool | None
    verified_categories: int
    mismatching_categories: int
    missing_categories: int
    effect: Proof
    reason_code: str

    @property
    def effect_confirmed(self) -> bool:
        return self.effect == Proof.CONFIRMED

    def as_report(self) -> dict[str, Any]:
        d = asdict(self)
        d["effect"] = self.effect.value
        d["effect_confirmed"] = self.effect_confirmed
        return d


def attest_filter(
    *, selected_label: str | None,
    retained_label: str | None,
    result_categories: Sequence[str | None] | None,
    official_total: int | None = None,
    trusted_category_source: bool = False,
    minimum_observed: int = 5,
) -> FilterEvidence:
    """Strong proof requires source-labelled categories from actual results.

    Use None rather than [] for unavailable categories. An empty official result
    set is not automatically proof of category filtering. The caller must have
    separately verified the category label's provenance from portal content.
    """
    if minimum_observed < 1:
        raise ValueError("INVALID_SAMPLE_THRESHOLD")
    selected = normalized_category(selected_label) == "fournitures"
    retained = None if retained_label is None else normalized_category(retained_label) == "fournitures"
    categories = list(result_categories or [])
    matching = sum(normalized_category(v) == "fournitures" for v in categories)
    missing = sum(normalized_category(v) == "" for v in categories)
    mismatch = len(categories) - matching - missing
    if not selected:
        effect, reason = Proof.UNCONFIRMED, "CATEGORY_SELECTION_NOT_CONFIRMED"
    elif retained is False:
        effect, reason = Proof.CONTRADICTED, "CATEGORY_NOT_RETAINED_AFTER_SEARCH"
    elif not trusted_category_source or not categories:
        effect, reason = Proof.UNCONFIRMED, "NO_INDEPENDENT_RESULT_CATEGORY_EVIDENCE"
    elif mismatch:
        effect, reason = Proof.CONTRADICTED, "NON_FOURNITURES_RESULT_OBSERVED"
    elif missing:
        effect, reason = Proof.UNCONFIRMED, "SOME_RESULT_CATEGORIES_MISSING"
    elif retained is not True:
        effect, reason = Proof.UNCONFIRMED, "POST_SEARCH_FILTER_STATE_UNKNOWN"
    elif not isinstance(official_total, int) or isinstance(official_total, bool) or official_total <= 0:
        effect, reason = Proof.UNCONFIRMED, "OFFICIAL_TOTAL_UNVERIFIED"
    elif len(categories) < min(minimum_observed, official_total):
        effect, reason = Proof.UNCONFIRMED, "INSUFFICIENT_CATEGORY_SAMPLE"
    else:
        effect, reason = Proof.CONFIRMED, "RESULT_CATEGORIES_MATCH_FOURNITURES"
    return FilterEvidence(selected, retained, matching, mismatch, missing, effect, reason)


async def observe_categories_in_cards(page: Any, *, selector_within_card: str) -> list[str | None]:
    """Collect public label text inside *each* displayed result card.

    This only extracts labels: a caller must validate the selector against real
    DOM evidence before setting trusted_category_source=True. No URLs or raw
    cards enter the report; missing/ambiguous markers become None.
    """
    if not selector_within_card or len(selector_within_card) > 120:
        raise ValueError("UNSAFE_OR_MISSING_RESULT_CATEGORY_SELECTOR")
    return await page.evaluate("""selector => {
      return [...document.querySelectorAll('.tender_item')].map(card => {
        const found = card.querySelectorAll(selector);
        return found.length === 1 ? (found[0].textContent || '').trim().slice(0, 80) : null;
      });
    }""", selector_within_card)


def can_start_collection(evidence: FilterEvidence) -> bool:
    """Never collect without independent proof of the requested category."""
    return evidence.effect_confirmed


async def select_fournitures_and_observe(
    page: Any,
    *,
    category_selector: str = "#ctl0_CONTENU_PAGE_AdvancedSearch_categorie",
    search_selector: str = "#ctl0_CONTENU_PAGE_AdvancedSearch_lancerRecherche",
    result_count_selector: str = "text=/Nombre de résultats/i",
    timeout_ms: int = 25000,
) -> dict[str, Any]:
    """Optional Playwright step, only after verified FORM_READY.

    It cannot infer per-result categories: those require a *separate* verified
    extractor. Returns an UNCONFIRMED report by default rather than success.
    """
    if not 1000 <= timeout_ms <= 60000:
        raise ValueError("UNSAFE_TIMEOUT")
    category = page.locator(category_selector)
    if await category.count() != 1:
        return attest_filter(selected_label=None, retained_label=None,
                             result_categories=None).as_report()
    await category.select_option(label="Fournitures", timeout=timeout_ms)
    selected_label = (await category.locator("option:checked").inner_text()).strip()
    if normalized_category(selected_label) != "fournitures":
        return attest_filter(selected_label=selected_label, retained_label=None,
                             result_categories=None).as_report()
    await page.locator(search_selector).click(timeout=timeout_ms)
    await page.locator(result_count_selector).first.wait_for(state="visible", timeout=timeout_ms)
    category_after = page.locator(category_selector)
    retained_label = None
    if await category_after.count() == 1:
        retained_label = (await category_after.locator("option:checked").inner_text()).strip()
    return attest_filter(
        selected_label=selected_label, retained_label=retained_label,
        result_categories=None, trusted_category_source=False,
    ).as_report()
