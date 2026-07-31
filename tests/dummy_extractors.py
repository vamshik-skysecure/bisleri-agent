"""
Rule-based extraction for the fixed dummy document templates provided for testing.
This is a STAND-IN for the real extraction step (Copilot Studio / Azure OpenAI parsing
unstructured emails+attachments) — it exists purely to feed realistic ExtractionResult
objects into the tracker pipeline so status/exception/matching logic can be tested
end-to-end without waiting on that integration.

Do not treat this as production extraction code — real supplier emails won't follow
a fixed template like this dummy set does.
"""
import re
import subprocess
from datetime import datetime
from pathlib import Path

import openpyxl

from app.models.tracker import ExtractionResult, UpdateType

# tracks batch -> PO linkage as documents are processed, so batch-only docs
# (no PO number in the body) can still resolve — mirrors "Option B" from the
# matching discussion: one linking document teaches the mapping for the rest.
BATCH_TO_PO: dict[str, str] = {}


def _pdf_text(path: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True
    ).stdout


def _qty(s: str) -> int:
    return int(re.sub(r"[^\d]", "", s))


def _date(s: str):
    for fmt in ("%d-%b-%Y",):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _po_from_text(text: str) -> str | None:
    m = re.search(r"BIS/PROC/2026/\d{4}", text)
    return m.group(0) if m else None


def _batch_from_text(text: str) -> str | None:
    m = re.search(r"BT\d{6}[A-Z]?", text)
    return m.group(0) if m else None


def parse_pdf(path: Path) -> ExtractionResult | None:
    text = _pdf_text(path)
    po = _po_from_text(text)
    batch = _batch_from_text(text)

    if po and batch:
        BATCH_TO_PO[batch] = po
    if not po and batch and batch in BATCH_TO_PO:
        po = BATCH_TO_PO[batch]

    if not po:
        return None  # nothing to anchor this document to — would go to review queue in real pipeline

    name = path.name

    # ---- Order Acknowledgement (1048 style — full table incl. supplier/co-packer/confirmed/required date) ----
    if "Order_Acknowledgement_PO_BIS_PROC_2026_1048" in name:
        return ExtractionResult(
            po_order=po,
            update_type=UpdateType.SUPPLIER_CONFIRMATION,
            po_date=_date(re.search(r"PO Date\s+(\S.+)", text).group(1)) if re.search(r"PO Date\s+(\S.+)", text) else None,
            supplier="AquaPack Industries Pvt. Ltd.",
            co_packer="FreshFill Co-Packers Pvt. Ltd.",
            material_sku="PET Preforms (28 mm)",
            ordered=50000,
            confirmed=50000,
            required_date=_date("05-Aug-2026"),
            remarks="Production planning completed. First dispatch scheduled 31-Jul-2026.",
            source_email_id=name,
            confidence=0.95,
        )

    # ---- Order Acknowledgement (1051 style — simpler layout) ----
    if "Order_Acknowledgement_PO_BIS_PROC_2026_1051" in name:
        return ExtractionResult(
            po_order=po,
            update_type=UpdateType.SUPPLIER_CONFIRMATION,
            supplier="EcoPlast Packaging Pvt. Ltd.",
            material_sku="Shrink Film Roll (500 mm)",
            ordered=25000,
            confirmed=25000,
            remarks="Order accepted. Production slot reserved, dispatch planned 06-Aug-2026.",
            source_email_id=name,
            confidence=0.93,
        )

    # ---- Dispatch Advice (1049 — table with ordered/dispatched/vehicle/eta) ----
    if "Dispatch_Advice_PO_BIS_PROC_2026_1049" in name:
        return ExtractionResult(
            po_order=po,
            update_type=UpdateType.DISPATCH,
            supplier="Prime Packaging Solutions Pvt. Ltd.",
            co_packer="Crystal Co-Packers Pvt. Ltd., Mysuru",
            material_sku="Bottle Caps 28mm",
            ordered=80000,
            dispatched=80000,
            remarks="Full quantity dispatched as per confirmed schedule.",
            source_email_id=name,
            confidence=0.94,
        )

    # ---- Dispatch Advice (1051) ----
    if "Dispatch_Advice_PO_BIS_PROC_2026_1051" in name:
        return ExtractionResult(
            po_order=po,
            update_type=UpdateType.DISPATCH,
            supplier="EcoPlast Packaging Pvt. Ltd.",
            material_sku="Shrink Film Roll (500 mm)",
            dispatched=25000,
            remarks="Full ordered quantity dispatched, sealed and handed to transporter.",
            source_email_id=name,
            confidence=0.95,
        )

    # ---- Delay Notification (1050) ----
    if "Delay_Notification_PO_BIS_PROC_2026_1050" in name:
        return ExtractionResult(
            po_order=po,
            update_type=UpdateType.DELAY_OR_BLOCK,
            supplier="Universal Polymers Pvt. Ltd.",
            material_sku="PET Bottle Caps 28 mm",
            required_date=None,
            remarks="Delay: unexpected maintenance shutdown. Dispatch revised 03-Aug-2026 -> 05-Aug-2026.",
            source_email_id=name,
            confidence=0.9,
        )

    # ---- Goods Receipt (1049) ----
    if "Goods_Receipt_PO_BIS_PROC_2026_1049" in name:
        return ExtractionResult(
            po_order=po,
            update_type=UpdateType.DELIVERY,
            supplier="Prime Packaging Solutions Pvt. Ltd.",
            co_packer="Crystal Co-Packers Pvt. Ltd., Mysuru",
            material_sku="Bottle Caps 28mm",
            received=80000,
            remarks="Accepted — no shortages or damage observed.",
            source_email_id=name,
            confidence=0.96,
        )

    # ---- Production Completion Report (BT240801A / PO 1048) ----
    if "Production_Completion_Report_BT240801A" in name:
        return ExtractionResult(
            po_order=po,
            update_type=UpdateType.FINISHED_GOODS_READY,
            co_packer="FreshFill Co-Packers Pvt. Ltd.",
            material_sku="PET Preforms (28 mm)",
            produced=50000,
            production_status_note="Completed — Line-2, 0 rejected",
            remarks=f"Production completion report, batch {batch}",
            source_email_id=name,
            confidence=0.95,
        )

    # ---- Finished Goods Dispatch Advice (BT240801A / PO 1048) ----
    # NOTE: this is FINISHED GOODS leaving the co-packer, not raw material —
    # deliberately NOT mapped to the raw-material `dispatched` field. See harness
    # output notes for why this exposes a real gap in the current tracker schema.
    if "Finished_Goods_Dispatch_Advice_BT240801A" in name:
        return ExtractionResult(
            po_order=po,
            update_type=UpdateType.OTHER,
            co_packer="FreshFill Co-Packers Pvt. Ltd.",
            remarks=f"Finished goods dispatched: 50,000 units (batch {batch}) — FG movement, not raw-material dispatch.",
            source_email_id=name,
            confidence=0.9,
        )

    # ---- Proof of Delivery (BT240801A / PO 1048) — FG delivered to distribution centre ----
    if "Proof_of_Delivery_BT240801A" in name:
        return ExtractionResult(
            po_order=po,
            update_type=UpdateType.ORDER_COMPLETED,
            remarks=f"POD confirmed — finished goods delivered to Bisleri Distribution Centre (batch {batch}).",
            source_email_id=name,
            confidence=0.92,
        )

    # ---- Delivery Confirmation (BT240801A) — NO PO or batch in body text at all ----
    if "Delivery_Confirmation_BT240801A" in name:
        # po resolved above via BATCH_TO_PO fallback if filename batch matched a known one —
        # but this file's *body* has neither PO nor batch, only filename. Real pipeline would
        # need the email subject/thread to resolve this; flagging that limitation explicitly.
        return ExtractionResult(
            po_order=po,
            update_type=UpdateType.ORDER_COMPLETED,
            remarks="Shipment received in good condition. Quantity verified: 50,000 units. No transit damage.",
            source_email_id=name,
            confidence=0.6,  # deliberately low — body text alone gives no anchor, only filename did
        )

    return None


def parse_xlsx(path: Path) -> ExtractionResult | None:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.worksheets[0]
    rows = [r for r in ws.iter_rows(values_only=True) if any(c is not None for c in r)]
    headers, data = rows[0], rows[1]
    record = dict(zip(headers, data))
    name = path.name

    if "Revised_Dispatch_Schedule" in name:
        po = record["PO"]
        return ExtractionResult(
            po_order=po,
            update_type=UpdateType.MATERIAL_PREPARATION,
            material_sku=record["Material"],
            ordered=int(record["Ordered Qty"]),
            remarks=f"Revised dispatch schedule: {record['Original Dispatch']} -> {record['Revised Dispatch']} ({record['Remarks']})",
            source_email_id=name,
            confidence=0.93,
        )

    if "Production_Schedule_BT240801A" in name:
        po = record["PO Number"]
        batch = record["Batch No"]
        BATCH_TO_PO[batch] = po
        return ExtractionResult(
            po_order=po,
            update_type=UpdateType.PRODUCTION_PLANNED,
            supplier=record["Supplier"],
            co_packer=record["Co-packer"],
            material_sku=record["Material / SKU"],
            remarks=f"Production scheduled — {record['Status']}, Line {record['Production Line']}",
            source_email_id=name,
            confidence=0.9,
        )

    if "Vehicle_Details_BT240801A" in name:
        po = record["PO"]
        batch = record["Batch"]
        BATCH_TO_PO[batch] = po
        return ExtractionResult(
            po_order=po,
            update_type=UpdateType.OTHER,
            remarks=f"FG vehicle dispatched — {record['Vehicle']}, ETA {record['ETA']} (batch {batch})",
            source_email_id=name,
            confidence=0.85,
        )

    return None


def parse_document(path: Path) -> ExtractionResult | None:
    if path.suffix.lower() == ".pdf":
        return parse_pdf(path)
    if path.suffix.lower() == ".xlsx":
        return parse_xlsx(path)
    return None
