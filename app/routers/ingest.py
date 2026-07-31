from fastapi import APIRouter, Depends, HTTPException

from app.models.tracker import ExtractionResult, RawEmailRequest
from app.security import require_api_key
from app.services.extraction_service import ExtractionServiceError, extract_email
from app.services.tracker_service import flag_for_review, upsert_tracker

router = APIRouter(prefix="/ingest", tags=["ingest"], dependencies=[Depends(require_api_key)])


@router.post("/email", summary="IngestStructuredEmail", operation_id="IngestStructuredEmail")
def ingest_structured_email(extraction: ExtractionResult):
    """Accept already-structured data from a prompt, connector, or manual test."""
    return upsert_tracker(extraction)


@router.post("/email/raw", summary="IngestRawEmail", operation_id="IngestRawEmail")
def ingest_raw_email(email: RawEmailRequest):
    """Extract a raw Power Automate email and attachments, then update SharePoint."""
    try:
        records = extract_email(email)
    except ExtractionServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not records:
        placeholder = ExtractionResult(
            po_order=None,
            source_email_id=email.message_id,
            confidence=0,
            remarks=f"No order record could be extracted from email: {email.subject}",
        )
        flag_for_review(placeholder, existing=None, reason="Azure OpenAI found no extractable order record")
        return {
            "message_id": email.message_id,
            "records_extracted": 0,
            "results": [{"action": "flagged_for_review", "po_order": None, "row": None}],
        }

    return {
        "message_id": email.message_id,
        "records_extracted": len(records),
        "results": [upsert_tracker(record) for record in records],
    }
