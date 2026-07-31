from fastapi import APIRouter, Depends

from app.config import settings
from app.models.tracker import ExceptionRecord
from app.security import require_api_key
from app.services.exception_engine import scan_exceptions
from app.services.field_mapping import sp_item_to_tracker_row
from app.services.history_service import status_age_days_by_po
from app.services.sharepoint_client import sharepoint_client

router = APIRouter(prefix="/exceptions", tags=["exceptions"], dependencies=[Depends(require_api_key)])


@router.get("", summary="ListExceptions", operation_id="ListExceptions", response_model=list[ExceptionRecord])
def list_exceptions():
    age_by_po = status_age_days_by_po()
    all_exceptions: list[ExceptionRecord] = []
    for item in sharepoint_client.get_items(settings.TRACKER_LIST_ID):
        row = sp_item_to_tracker_row(item)
        all_exceptions.extend(scan_exceptions(row, age_by_po.get(row.po_order, 0)))
    return all_exceptions
