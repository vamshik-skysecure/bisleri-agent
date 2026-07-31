"""Confirmed internal column names for the Bisleri Tracker SharePoint list."""
from app.models.tracker import TrackerRow, CurrentStatus, Owner
from datetime import date

# Application field -> confirmed internal SharePoint field name.
FIELD_MAP = {
    "po_order": "Title",                 # PO/Order is the Title column
    "po_date": "PODate",
    "supplier": "Supplier",
    "co_packer": "Co_x002d_packer",
    "material_sku": "Material_x002f_SKU",
    "ordered": "Ordered",
    "confirmed": "Confirmed",
    "dispatched": "Dispatched",
    "received": "Received",
    "produced": "Produced",
    "pending": "Pending",
    "required_date": "RequiredDate",
    "expected_dispatch_date": "ExpectedDispatchDate",
    "expected_delivery_date": "ExpectedDeliveryDate",
    "production_status_note": "ProductionStatusNote",
    "remarks": "Remarks",
    "current_status": "CurrentStatus",
    "next_action": "NextAction",
    "owner": "Owner",
}


def tracker_row_to_sp_fields(row: TrackerRow) -> dict:
    fields = {
        FIELD_MAP["po_order"]: row.po_order,
        FIELD_MAP["po_date"]: row.po_date.isoformat() if row.po_date else None,
        FIELD_MAP["supplier"]: row.supplier,
        FIELD_MAP["co_packer"]: row.co_packer,
        FIELD_MAP["material_sku"]: row.material_sku,
        FIELD_MAP["ordered"]: row.ordered,
        FIELD_MAP["confirmed"]: row.confirmed,
        FIELD_MAP["dispatched"]: row.dispatched,
        FIELD_MAP["received"]: row.received,
        FIELD_MAP["produced"]: row.produced,
        FIELD_MAP["pending"]: row.pending,
        FIELD_MAP["current_status"]: row.current_status.value,
        FIELD_MAP["next_action"]: row.next_action,
        f"{FIELD_MAP['owner']}@odata.type": "Collection(Edm.String)",
        FIELD_MAP["owner"]: [o.value for o in row.owner],
        FIELD_MAP["expected_dispatch_date"]: (
            row.expected_dispatch_date.isoformat() if row.expected_dispatch_date else None
        ),
        FIELD_MAP["expected_delivery_date"]: (
            row.expected_delivery_date.isoformat() if row.expected_delivery_date else None
        ),
        FIELD_MAP["production_status_note"]: row.production_status_note,
        FIELD_MAP["remarks"]: row.remarks,
    }
    if row.required_date:
        fields[FIELD_MAP["required_date"]] = row.required_date.isoformat()
    return {k: v for k, v in fields.items() if v is not None}


def sp_item_to_tracker_row(item: dict) -> TrackerRow:
    f = item["fields"]
    req_date = f.get(FIELD_MAP["required_date"])
    po_date = f.get(FIELD_MAP["po_date"])
    expected_dispatch = f.get(FIELD_MAP["expected_dispatch_date"])
    expected_delivery = f.get(FIELD_MAP["expected_delivery_date"])
    return TrackerRow(
        po_order=f.get(FIELD_MAP["po_order"], ""),
        po_date=date.fromisoformat(po_date[:10]) if po_date else None,
        supplier=f.get(FIELD_MAP["supplier"]),
        co_packer=f.get(FIELD_MAP["co_packer"]),
        material_sku=f.get(FIELD_MAP["material_sku"]),
        ordered=int(f.get(FIELD_MAP["ordered"], 0) or 0),
        confirmed=int(f.get(FIELD_MAP["confirmed"], 0) or 0),
        dispatched=int(f.get(FIELD_MAP["dispatched"], 0) or 0),
        received=int(f.get(FIELD_MAP["received"], 0) or 0),
        produced=int(f.get(FIELD_MAP["produced"], 0) or 0),
        pending=int(f.get(FIELD_MAP["pending"], 0) or 0),
        required_date=date.fromisoformat(req_date[:10]) if req_date else None,
        expected_dispatch_date=(date.fromisoformat(expected_dispatch[:10]) if expected_dispatch else None),
        expected_delivery_date=(date.fromisoformat(expected_delivery[:10]) if expected_delivery else None),
        production_status_note=f.get(FIELD_MAP["production_status_note"]),
        remarks=f.get(FIELD_MAP["remarks"]),
        current_status=CurrentStatus(f.get(FIELD_MAP["current_status"], CurrentStatus.PO_ISSUED.value)),
        next_action=f.get(FIELD_MAP["next_action"]),
        owner=[Owner(o) for o in f.get(FIELD_MAP["owner"], []) or []],
        sharepoint_item_id=item.get("id"),
    )
