from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.config import settings
from app.security import require_api_key
from app.services.exception_engine import scan_exceptions
from app.services.field_mapping import sp_item_to_tracker_row
from app.services.history_service import status_age_days_by_po
from app.services.sharepoint_client import sharepoint_client

router = APIRouter(prefix="/report", tags=["report"], dependencies=[Depends(require_api_key)])


@router.post("/generate", summary="GenerateSnapshot", operation_id="GenerateSnapshot")
def generate_snapshot():
    rows = [
        sp_item_to_tracker_row(item)
        for item in sharepoint_client.get_items(settings.TRACKER_LIST_ID)
    ]
    age_by_po = status_age_days_by_po()
    all_exceptions = [
        exception
        for row in rows
        for exception in scan_exceptions(row, age_by_po.get(row.po_order, 0))
    ]
    owner_actions = Counter(owner.value for row in rows for owner in row.owner)
    ageing = Counter(
        "0-2 days" if age_by_po.get(row.po_order, 0) <= 2
        else "3-7 days" if age_by_po.get(row.po_order, 0) <= 7
        else "8+ days"
        for row in rows
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_orders": len(rows),
        "quantity_totals": {
            "ordered": sum(row.ordered for row in rows),
            "confirmed": sum(row.confirmed for row in rows),
            "dispatched": sum(row.dispatched for row in rows),
            "received": sum(row.received for row in rows),
            "produced": sum(row.produced for row in rows),
            "pending": sum(row.pending for row in rows),
        },
        "status_breakdown": dict(Counter(row.current_status.value for row in rows)),
        "ageing_breakdown": dict(ageing),
        "actions_by_owner": dict(owner_actions),
        "total_exceptions": len(all_exceptions),
        "high_severity_exceptions": [
            item.model_dump(mode="json") for item in all_exceptions if item.severity == "high"
        ],
        "all_exceptions": [item.model_dump(mode="json") for item in all_exceptions],
        "pending_actions": [
            {
                "po_order": row.po_order,
                "status": row.current_status.value,
                "next_action": row.next_action,
                "owners": [owner.value for owner in row.owner],
                "days_in_status": age_by_po.get(row.po_order, 0),
            }
            for row in rows
            if row.next_action and row.current_status.value != "Order Completed"
        ],
    }
