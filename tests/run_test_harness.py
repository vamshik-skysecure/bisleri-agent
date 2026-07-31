"""
Run all dummy test documents through the REAL tracker pipeline (matcher, status
engine, exception engine, tracker_service) using a mock SharePoint store.

Usage:
    cd bisleri-tracker-agent
    python3 -m tests.run_test_harness
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
import app.services.sharepoint_client as sp_module
from tests.mock_sharepoint import MockSharePointClient
from tests.dummy_extractors import parse_document

# ---- swap in the mock BEFORE importing anything that already bound a reference to it ----
mock = MockSharePointClient()
sp_module.sharepoint_client.get_items = mock.get_items
sp_module.sharepoint_client.get_item_by_po = mock.get_item_by_po
sp_module.sharepoint_client.create_item = mock.create_item
sp_module.sharepoint_client.update_item = mock.update_item

from app.services.tracker_service import upsert_tracker  # noqa: E402  (import after monkeypatch)
from app.services.field_mapping import sp_item_to_tracker_row  # noqa: E402
from app.services.exception_engine import scan_exceptions  # noqa: E402

settings.TRACKER_LIST_ID = "tracker"
settings.HISTORY_LIST_ID = "history"
settings.REVIEW_LIST_ID = "review"
settings.LOW_CONFIDENCE_THRESHOLD = 0.75  # matches config default — Delivery_Confirmation (0.6) should get flagged

TEST_DATA_DIR = Path(__file__).resolve().parent.parent / "test_data"

# Process in a realistic chronological order (mirrors when each doc would actually arrive)
PROCESSING_ORDER = [
    "Order_Acknowledgement_PO_BIS_PROC_2026_1048.pdf",
    "Order_Acknowledgement_PO_BIS_PROC_2026_1051.pdf",
    "Revised_Dispatch_Schedule_PO_BIS_PROC_2026_1050.xlsx",
    "Delay_Notification_PO_BIS_PROC_2026_1050.pdf",
    "Dispatch_Advice_PO_BIS_PROC_2026_1051.pdf",
    "Dispatch_Advice_PO_BIS_PROC_2026_1049.pdf",
    "Goods_Receipt_PO_BIS_PROC_2026_1049.pdf",
    "Production_Schedule_BT240801A.xlsx",
    "Production_Completion_Report_BT240801A.pdf",
    "Vehicle_Details_BT240801A.xlsx",
    "Finished_Goods_Dispatch_Advice_BT240801A(1).pdf",
    "Proof_of_Delivery_BT240801A.pdf",
    "Delivery_Confirmation_BT240801A.pdf",
]


def main():
    print("=" * 90)
    print("PROCESSING DOCUMENTS")
    print("=" * 90)

    for filename in PROCESSING_ORDER:
        path = TEST_DATA_DIR / filename
        if not path.exists():
            print(f"[SKIP] {filename} — not found in test_data/")
            continue

        extraction = parse_document(path)
        if extraction is None:
            print(f"[SKIP] {filename} — no PO/batch anchor found, would go to raw-review in real pipeline")
            continue

        result = upsert_tracker(extraction)
        print(f"\n--- {filename} ---")
        print(f"  extracted PO: {extraction.po_order} | confidence: {extraction.confidence}")
        print(f"  action: {result['action']}")
        if result["row"]:
            row = result["row"]
            print(f"  status: {row.current_status.value} | next action: {row.next_action}")

    print("\n" + "=" * 90)
    print("FINAL TRACKER STATE")
    print("=" * 90)
    print(f"{'PO':<22}{'Ordered':>8}{'Dispatch':>9}{'Received':>9}{'Produced':>9}{'Pending':>8}  Status")
    for item in mock.dump("tracker"):
        row = sp_item_to_tracker_row(item)
        print(f"{row.po_order:<22}{row.ordered:>8}{row.dispatched:>9}{row.received:>9}"
              f"{row.produced:>9}{row.pending:>8}  {row.current_status.value}")

    print("\n" + "=" * 90)
    print("EXCEPTIONS")
    print("=" * 90)
    for item in mock.dump("tracker"):
        row = sp_item_to_tracker_row(item)
        exs = scan_exceptions(row, days_in_current_status=1)
        for e in exs:
            print(f"  {row.po_order}: [{e.severity.upper()}] {e.exception_type.value} — {e.recommended_action}")

    print("\n" + "=" * 90)
    print("REVIEW QUEUE (flagged records)")
    print("=" * 90)
    for item in mock.dump("review"):
        print(f"  PO: {item['fields']['Title']} | Reason: {item['fields']['ConflictReason']}")

    print("\n" + "=" * 90)
    print("HISTORY LOG (change trail)")
    print("=" * 90)
    for item in mock.dump("history"):
        f = item["fields"]
        print(f"  {f['Title']:<22} {f['FieldChanged']:<16} {f['OldValue']!s:>10} -> {f['NewValue']!s:<10} "
              f"(src: {f['SourceEmail']})")


if __name__ == "__main__":
    main()
