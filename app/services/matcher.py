from rapidfuzz import fuzz

from app.config import settings
from app.models.tracker import ExtractionResult, TrackerRow
from app.services.field_mapping import sp_item_to_tracker_row
from app.services.sharepoint_client import sharepoint_client

FUZZY_MATCH_THRESHOLD = 85
AMBIGUITY_MARGIN = 8


def _candidate_score(extraction: ExtractionResult, row: TrackerRow) -> float:
    score = 0.0
    if extraction.supplier and row.supplier:
        score += fuzz.token_sort_ratio(extraction.supplier, row.supplier) * 0.45
    if extraction.material_sku and row.material_sku:
        score += fuzz.token_sort_ratio(extraction.material_sku, row.material_sku) * 0.45
    if extraction.required_date and row.required_date:
        day_difference = abs((extraction.required_date - row.required_date).days)
        score += max(10 - min(day_difference, 10), 0)
    return score


def find_matching_row(extraction: ExtractionResult) -> TrackerRow | None:
    """Use exact PO first; accept fuzzy fallback only when the winner is unambiguous."""
    if extraction.po_order:
        item = sharepoint_client.get_item_by_po(settings.TRACKER_LIST_ID, extraction.po_order)
        if item:
            return sp_item_to_tracker_row(item)

    ranked = sorted(
        (
            (_candidate_score(extraction, row), row)
            for row in (
                sp_item_to_tracker_row(item)
                for item in sharepoint_client.get_items(settings.TRACKER_LIST_ID)
            )
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not ranked or ranked[0][0] < FUZZY_MATCH_THRESHOLD:
        return None
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < AMBIGUITY_MARGIN:
        return None
    return ranked[0][1]
