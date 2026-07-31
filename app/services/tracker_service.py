from app.models.tracker import ExtractionResult, HistoryEntry, ReviewQueueEntry, TrackerRow
from app.services.field_mapping import tracker_row_to_sp_fields
from app.services.history_service import source_email_already_processed
from app.services.matcher import find_matching_row
from app.services.sharepoint_client import sharepoint_client
from app.services.status_engine import evaluate_status
from app.config import settings


CONFLICT_SENSITIVE_FIELDS = ["ordered", "confirmed", "dispatched", "received", "produced"]
PERSISTED_EXTRACTION_FIELDS = [
    "po_date",
    "supplier",
    "co_packer",
    "material_sku",
    "ordered",
    "confirmed",
    "dispatched",
    "received",
    "produced",
    "required_date",
    "expected_dispatch_date",
    "expected_delivery_date",
    "production_status_note",
    "remarks",
]


def _detect_conflicts(existing: TrackerRow, extraction: ExtractionResult) -> list[str]:
    conflicts = []
    for field in CONFLICT_SENSITIVE_FIELDS:
        new_val = getattr(extraction, field, None)
        old_val = getattr(existing, field, None)
        if new_val is not None and old_val not in (None, 0) and new_val < old_val:
            conflicts.append(f"{field}: existing={old_val}, new={new_val}")
    return conflicts


def _pending(row: TrackerRow) -> int:
    # Confirmation is a commitment, not physical fulfilment. Pending falls only as
    # dispatch/receipt/production progresses through the operational stages.
    furthest_progress = max(row.dispatched, row.received, row.produced)
    return max(row.ordered - furthest_progress, 0)


def upsert_tracker(extraction: ExtractionResult, force: bool = False) -> dict:
    """Create/update a tracker record with conflict review, audit, and idempotency."""
    existing = find_matching_row(extraction)
    effective_po = existing.po_order if existing else extraction.po_order

    if source_email_already_processed(effective_po, extraction.source_email_id) and not force:
        return {
            "action": "duplicate_ignored",
            "po_order": effective_po,
            "row": existing,
        }

    if not extraction.po_order and existing is None:
        flag_for_review(extraction, existing=None, reason="No PO/order number and no safe fuzzy match")
        return {"action": "flagged_for_review", "po_order": None, "row": None}

    if extraction.confidence < settings.LOW_CONFIDENCE_THRESHOLD and not force:
        flag_for_review(extraction, existing=existing, reason="Low extraction confidence")
        return {"action": "flagged_for_review", "po_order": effective_po, "row": existing}

    if existing is None:
        row = TrackerRow(
            po_order=extraction.po_order or "",
            po_date=extraction.po_date,
            supplier=extraction.supplier,
            co_packer=extraction.co_packer,
            material_sku=extraction.material_sku,
            ordered=extraction.ordered or 0,
            confirmed=extraction.confirmed or 0,
            dispatched=extraction.dispatched or 0,
            received=extraction.received or 0,
            produced=extraction.produced or 0,
            required_date=extraction.required_date,
            expected_dispatch_date=extraction.expected_dispatch_date,
            expected_delivery_date=extraction.expected_delivery_date,
            production_status_note=extraction.production_status_note,
            remarks=extraction.remarks,
        )
        row.pending = _pending(row)
        row.current_status, row.next_action, row.owner = evaluate_status(row, extraction.update_type)

        created = sharepoint_client.create_item(settings.TRACKER_LIST_ID, tracker_row_to_sp_fields(row))
        row.sharepoint_item_id = created.get("id")
        _log_history(row.po_order, "record", None, "created", extraction.source_email_id)
        _log_history(row.po_order, "current_status", None, row.current_status.value, extraction.source_email_id)
        _log_history(row.po_order, "update_type", None, extraction.update_type.value, extraction.source_email_id)
        return {"action": "created", "po_order": row.po_order, "row": row}

    conflicts = _detect_conflicts(existing, extraction)
    if conflicts and not force:
        flag_for_review(extraction, existing=existing, reason="; ".join(conflicts))
        return {"action": "flagged_for_review", "po_order": existing.po_order, "row": existing}

    updated = existing.model_copy(deep=True)
    changed_fields: list[tuple[str, object, object]] = []
    for field in PERSISTED_EXTRACTION_FIELDS:
        new_val = getattr(extraction, field, None)
        old_val = getattr(existing, field, None)
        if new_val is not None and new_val != old_val:
            setattr(updated, field, new_val)
            changed_fields.append((field, old_val, new_val))

    new_pending = _pending(updated)
    if new_pending != updated.pending:
        changed_fields.append(("pending", updated.pending, new_pending))
        updated.pending = new_pending

    status, next_action, owners = evaluate_status(updated, extraction.update_type)
    if status != updated.current_status:
        changed_fields.append(("current_status", updated.current_status.value, status.value))
    if next_action != updated.next_action:
        changed_fields.append(("next_action", updated.next_action, next_action))
    if owners != updated.owner:
        changed_fields.append(("owner", [o.value for o in updated.owner], [o.value for o in owners]))
    updated.current_status, updated.next_action, updated.owner = status, next_action, owners

    if changed_fields:
        sharepoint_client.update_item(
            settings.TRACKER_LIST_ID,
            existing.sharepoint_item_id,
            tracker_row_to_sp_fields(updated),
        )
        for field, old_val, new_val in changed_fields:
            _log_history(updated.po_order, field, _stringify(old_val), _stringify(new_val), extraction.source_email_id)

    _log_history(
        updated.po_order,
        "update_type",
        None,
        extraction.update_type.value,
        extraction.source_email_id,
    )
    return {"action": "updated", "po_order": updated.po_order, "row": updated}


def _stringify(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _log_history(po_order: str, field: str, old_val, new_val, source_email_id: str):
    entry = HistoryEntry(
        po_order=po_order,
        field_changed=field,
        old_value=old_val,
        new_value=new_val,
        source_email_id=source_email_id,
    )
    sharepoint_client.create_item(settings.HISTORY_LIST_ID, {
        "Title": entry.po_order,
        "FieldChanged": entry.field_changed,
        "OldValue": entry.old_value,
        "NewValue": entry.new_value,
        "SourceEmail": entry.source_email_id,
        "ChangedBy": entry.changed_by,
        "Timestamp": entry.timestamp.isoformat(),
    })


def flag_for_review(extraction: ExtractionResult, existing: TrackerRow | None, reason: str):
    title = extraction.po_order or f"UNMATCHED-{extraction.source_email_id}"
    title = title[:255]
    entry = ReviewQueueEntry(
        po_order=title,
        conflict_reason=reason,
        extraction=extraction,
        existing_row=existing,
    )
    sharepoint_client.create_item(settings.REVIEW_LIST_ID, {
        "Title": entry.po_order,
        "ConflictReason": entry.conflict_reason,
        "ExtractedData": entry.extraction.model_dump_json(),
        "Reviewed": False,
    })
