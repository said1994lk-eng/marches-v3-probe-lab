"""Pure, conservative decision gate for sampled post-search category evidence.

Full coverage (all official results/page transitions) is a separate later gate.
This evaluates only whether a bounded sample supports Fournitures filtering.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from category_evidence import CategorySample


@dataclass(frozen=True)
class GateDecision:
    status: str
    reason: str
    selected: bool
    retained_after_search: bool | None
    search_response_seen: bool
    result_transition_seen: bool
    official_total: int | None
    sample_size: int
    verified_fournitures: int
    contradictions: int
    unknown: int

    def report(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_gate(*, selected: bool, retained: bool | None,
                  search_response_seen: bool, result_transition_seen: bool,
                  official_total: int | None, sample: CategorySample,
                  minimum_sample: int = 5) -> GateDecision:
    """Strictly refuse success from dropdown selection, count or topic words."""
    if not 1 <= minimum_sample <= 10:
        raise ValueError('INVALID_MINIMUM_SAMPLE')
    valid_total = (isinstance(official_total, int) and not isinstance(official_total, bool)
                   and official_total > 0)
    valid_response = search_response_seen or result_transition_seen
    if not selected:
        status, reason = 'UNCONFIRMED', 'CATEGORY_NOT_SELECTED'
    elif retained is False:
        status, reason = 'CONTRADICTED', 'CATEGORY_NOT_RETAINED'
    elif sample.mismatching:
        status, reason = 'CONTRADICTED', 'OTHER_CATEGORY_OBSERVED'
    elif not valid_total:
        status, reason = 'UNCONFIRMED', 'OFFICIAL_TOTAL_MISSING_OR_ZERO'
    elif not valid_response:
        status, reason = 'UNCONFIRMED', 'SEARCH_UPDATE_NOT_OBSERVED'
    elif sample.cards_observed < min(minimum_sample, official_total):
        status, reason = 'UNCONFIRMED', 'INSUFFICIENT_RESULT_CARDS'
    elif sample.matching < min(minimum_sample, official_total) or sample.missing:
        status, reason = 'UNCONFIRMED', 'INDEPENDENT_CATEGORY_EVIDENCE_INCOMPLETE'
    else:
        status, reason = 'SAMPLED_CONFIRMED', 'INDEPENDENT_FOURNITURES_SAMPLE_CONFIRMED'
    return GateDecision(status, reason, selected, retained, search_response_seen,
                        result_transition_seen, official_total, sample.cards_observed,
                        sample.matching, sample.mismatching, sample.missing)