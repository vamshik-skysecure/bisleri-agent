from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import settings
from app.models.tracker import ExtractionResult, TrackerRow
from app.security import require_api_key
from app.services.field_mapping import sp_item_to_tracker_row
from app.services.sharepoint_client import sharepoint_client
from app.services.tracker_service import upsert_tracker

router = APIRouter(prefix="/tracker", tags=["tracker"], dependencies=[Depends(require_api_key)])


@router.post("/upsert", summary="UpsertTrackerRow", operation_id="UpsertTrackerRow")
def upsert(extraction: ExtractionResult):
    return upsert_tracker(extraction)


@router.get("/order", summary="GetOrderStatus", operation_id="GetOrderStatus", response_model=TrackerRow)
def get_order(po_order: str = Query(description="Full PO/order number; slashes are supported")):
    item = sharepoint_client.get_item_by_po(settings.TRACKER_LIST_ID, po_order)
    if not item:
        raise HTTPException(status_code=404, detail=f"PO/Order '{po_order}' not found in tracker")
    return sp_item_to_tracker_row(item)


@router.get("", summary="ListTracker", operation_id="ListTracker", response_model=list[TrackerRow])
def list_tracker():
    items = sharepoint_client.get_items(settings.TRACKER_LIST_ID)
    return [sp_item_to_tracker_row(item) for item in items]


@router.get("/{po_order:path}", include_in_schema=False, response_model=TrackerRow)
def get_order_legacy(po_order: str):
    """Backward-compatible route; new integrations should use /tracker/order?po_order=."""
    return get_order(po_order)
