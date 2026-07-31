import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import settings
from app.models.tracker import ReviewResolution
from app.security import require_api_key
from app.services.sharepoint_client import sharepoint_client
from app.services.tracker_service import upsert_tracker

router = APIRouter(prefix="/reviews", tags=["reviews"], dependencies=[Depends(require_api_key)])


@router.get("", summary="ListReviewQueue", operation_id="ListReviewQueue")
def list_reviews(reviewed: bool | None = Query(default=False)):
    results = []
    for item in sharepoint_client.get_items(settings.REVIEW_LIST_ID):
        fields = item.get("fields", {})
        if reviewed is not None and bool(fields.get("Reviewed", False)) != reviewed:
            continue
        extracted = fields.get("ExtractedData")
        try:
            extracted = json.loads(extracted) if extracted else None
        except json.JSONDecodeError:
            pass
        results.append({
            "item_id": item.get("id"),
            "po_order": fields.get("Title"),
            "conflict_reason": fields.get("ConflictReason"),
            "extracted_data": extracted,
            "reviewed": bool(fields.get("Reviewed", False)),
            "reviewed_by": fields.get("ReviewedBy"),
            "reviewed_date": fields.get("ReviewedDate"),
        })
    return results


@router.post("/{item_id}/resolve", summary="ResolveReview", operation_id="ResolveReview")
def resolve_review(item_id: str, resolution: ReviewResolution):
    review_item = sharepoint_client.get_item(settings.REVIEW_LIST_ID, item_id)
    if not review_item:
        raise HTTPException(status_code=404, detail=f"Review item '{item_id}' not found")
    if review_item.get("fields", {}).get("Reviewed"):
        raise HTTPException(status_code=409, detail=f"Review item '{item_id}' is already resolved")

    result = upsert_tracker(resolution.corrected_extraction, force=True)
    reviewed_date = datetime.now(timezone.utc).isoformat()
    sharepoint_client.update_item(settings.REVIEW_LIST_ID, item_id, {
        "Reviewed": True,
        "ReviewedBy": resolution.reviewed_by,
        "ReviewedDate": reviewed_date,
    })
    return {"review_item_id": item_id, "reviewed_date": reviewed_date, "result": result}
