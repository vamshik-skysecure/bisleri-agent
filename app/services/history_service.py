from datetime import date, datetime, timezone

from app.config import settings
from app.services.sharepoint_client import sharepoint_client


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def source_email_already_processed(po_order: str | None, source_email_id: str) -> bool:
    """Idempotency check: the same source email is processed once per PO."""
    if not source_email_id:
        return False
    for item in sharepoint_client.get_items(settings.HISTORY_LIST_ID):
        fields = item.get("fields", {})
        if fields.get("SourceEmail") != source_email_id:
            continue
        if po_order is None or fields.get("Title") == po_order:
            return True
    return False


def status_age_days_by_po() -> dict[str, int]:
    """Calculate current-stage ageing from the latest status/history event per PO."""
    latest: dict[str, datetime] = {}
    for item in sharepoint_client.get_items(settings.HISTORY_LIST_ID):
        fields = item.get("fields", {})
        po_order = fields.get("Title")
        changed = str(fields.get("FieldChanged", "")).casefold()
        if not po_order or changed not in {"current_status", "record"}:
            continue
        timestamp = _parse_timestamp(fields.get("Timestamp"))
        if timestamp and (po_order not in latest or timestamp > latest[po_order]):
            latest[po_order] = timestamp

    today = date.today()
    return {po: max((today - timestamp.date()).days, 0) for po, timestamp in latest.items()}
