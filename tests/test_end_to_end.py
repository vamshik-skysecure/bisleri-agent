import base64
import io
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import openpyxl
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.tracker import (
    CurrentStatus,
    EmailAttachment,
    ExtractionResult,
    RawEmailRequest,
    TrackerRow,
    UpdateType,
)
from app.services.extraction_service import build_model_content, extract_email
from app.services.field_mapping import sp_item_to_tracker_row
from app.services.history_service import status_age_days_by_po
from app.services.sharepoint_client import sharepoint_client
from app.services.status_engine import evaluate_status
from app.services.tracker_service import upsert_tracker
from tests.mock_sharepoint import MockSharePointClient


class StatusEngineTests(unittest.TestCase):
    def test_every_declared_status_is_reachable(self):
        row = TrackerRow(po_order="PO-1", ordered=100)
        cases = {
            UpdateType.PO_ISSUED: CurrentStatus.PO_ISSUED,
            UpdateType.CONFIRMATION_PENDING: CurrentStatus.SUPPLIER_CONFIRMATION_PENDING,
            UpdateType.SUPPLIER_CONFIRMATION: CurrentStatus.MATERIAL_UNDER_PREPARATION,
            UpdateType.DISPATCH: CurrentStatus.MATERIAL_DISPATCHED,
            UpdateType.DELIVERY: CurrentStatus.DELIVERED_TO_COPACKER,
            UpdateType.PRODUCTION_PLANNED: CurrentStatus.PRODUCTION_PLANNED,
            UpdateType.PRODUCTION_STARTED: CurrentStatus.PRODUCTION_IN_PROGRESS,
            UpdateType.FINISHED_GOODS_READY: CurrentStatus.FINISHED_GOODS_READY,
            UpdateType.PARTIAL_COMPLETION: CurrentStatus.PARTIALLY_COMPLETED,
            UpdateType.DELAY_OR_BLOCK: CurrentStatus.DELAYED_OR_BLOCKED,
            UpdateType.ORDER_COMPLETED: CurrentStatus.ORDER_COMPLETED,
        }
        for update_type, expected_status in cases.items():
            with self.subTest(update_type=update_type):
                status, _, _ = evaluate_status(row, update_type)
                self.assertEqual(status, expected_status)


class MockedPipelineTests(unittest.TestCase):
    def setUp(self):
        self.mock = MockSharePointClient()
        self.original_settings = {
            "TRACKER_LIST_ID": settings.TRACKER_LIST_ID,
            "HISTORY_LIST_ID": settings.HISTORY_LIST_ID,
            "REVIEW_LIST_ID": settings.REVIEW_LIST_ID,
            "LOW_CONFIDENCE_THRESHOLD": settings.LOW_CONFIDENCE_THRESHOLD,
            "API_KEY": settings.API_KEY,
        }
        settings.TRACKER_LIST_ID = "tracker"
        settings.HISTORY_LIST_ID = "history"
        settings.REVIEW_LIST_ID = "review"
        settings.LOW_CONFIDENCE_THRESHOLD = 0.75
        settings.API_KEY = "test-api-key"
        self.patchers = [
            patch.object(sharepoint_client, "get_items", new=self.mock.get_items),
            patch.object(sharepoint_client, "get_item_by_po", new=self.mock.get_item_by_po),
            patch.object(sharepoint_client, "get_item", new=self.mock.get_item),
            patch.object(sharepoint_client, "create_item", new=self.mock.create_item),
            patch.object(sharepoint_client, "update_item", new=self.mock.update_item),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        for name, value in self.original_settings.items():
            setattr(settings, name, value)

    def test_complete_order_lifecycle_and_duplicate_protection(self):
        po = "BIS/PROC/2026/2001"
        acknowledgement = ExtractionResult(
            po_order=po,
            update_type=UpdateType.SUPPLIER_CONFIRMATION,
            po_date=date(2026, 7, 31),
            supplier="Demo Supplier",
            co_packer="Demo Co-packer",
            material_sku="SKU-1",
            ordered=1000,
            confirmed=1000,
            required_date=date(2026, 8, 20),
            remarks="Confirmed in full",
            source_email_id="mail-ack",
            confidence=0.98,
        )
        created = upsert_tracker(acknowledgement)
        self.assertEqual(created["action"], "created")
        self.assertEqual(created["row"].current_status, CurrentStatus.MATERIAL_UNDER_PREPARATION)
        self.assertEqual(created["row"].pending, 1000)
        self.assertEqual(upsert_tracker(acknowledgement)["action"], "duplicate_ignored")

        stages = [
            ("mail-dispatch", UpdateType.DISPATCH, {"dispatched": 1000}, CurrentStatus.MATERIAL_DISPATCHED),
            ("mail-delivery", UpdateType.DELIVERY, {"received": 1000}, CurrentStatus.DELIVERED_TO_COPACKER),
            ("mail-plan", UpdateType.PRODUCTION_PLANNED, {}, CurrentStatus.PRODUCTION_PLANNED),
            ("mail-start", UpdateType.PRODUCTION_STARTED, {"produced": 400}, CurrentStatus.PRODUCTION_IN_PROGRESS),
            ("mail-ready", UpdateType.FINISHED_GOODS_READY, {"produced": 1000}, CurrentStatus.FINISHED_GOODS_READY),
            ("mail-close", UpdateType.ORDER_COMPLETED, {}, CurrentStatus.ORDER_COMPLETED),
        ]
        for source, update_type, quantities, expected_status in stages:
            result = upsert_tracker(ExtractionResult(
                po_order=po,
                update_type=update_type,
                source_email_id=source,
                confidence=0.98,
                **quantities,
            ))
            self.assertEqual(result["row"].current_status, expected_status)

        final = sp_item_to_tracker_row(self.mock.get_item_by_po("tracker", po))
        self.assertEqual(final.current_status, CurrentStatus.ORDER_COMPLETED)
        self.assertEqual(final.confirmed, 1000)
        self.assertEqual(final.produced, 1000)
        self.assertEqual(final.pending, 0)

    def test_low_confidence_review_can_be_resolved(self):
        extraction = ExtractionResult(
            po_order="PO-REVIEW-1",
            update_type=UpdateType.DISPATCH,
            ordered=100,
            dispatched=80,
            source_email_id="uncertain-mail",
            confidence=0.4,
        )
        result = upsert_tracker(extraction)
        self.assertEqual(result["action"], "flagged_for_review")
        review_item = self.mock.dump("review")[0]

        client = TestClient(app)
        response = client.post(
            f"/reviews/{review_item['id']}/resolve",
            headers={"X-API-Key": "test-api-key"},
            json={
                "reviewed_by": "demo.reviewer@company.com",
                "corrected_extraction": {
                    **extraction.model_dump(mode="json"),
                    "dispatched": 100,
                    "confidence": 1.0,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(self.mock.get_item("review", review_item["id"])["fields"]["Reviewed"])
        self.assertEqual(len(self.mock.dump("tracker")), 1)

    def test_api_key_and_slash_po_query(self):
        upsert_tracker(ExtractionResult(
            po_order="BIS/PROC/2026/3001",
            update_type=UpdateType.PO_ISSUED,
            supplier="Supplier",
            material_sku="SKU",
            ordered=10,
            source_email_id="mail-3001",
            confidence=1,
        ))
        client = TestClient(app)
        self.assertEqual(client.get("/tracker").status_code, 401)
        response = client.get(
            "/tracker/order",
            params={"po_order": "BIS/PROC/2026/3001"},
            headers={"X-API-Key": "test-api-key"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["po_order"], "BIS/PROC/2026/3001")

    def test_history_age_is_calculated(self):
        timestamp = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        self.mock.create_item("history", {
            "Title": "PO-AGE-1",
            "FieldChanged": "current_status",
            "OldValue": "PO Issued",
            "NewValue": "Supplier Confirmation Pending",
            "SourceEmail": "age-mail",
            "ChangedBy": "agent",
            "Timestamp": timestamp,
        })
        self.assertEqual(status_age_days_by_po()["PO-AGE-1"], 5)


class RawExtractionTests(unittest.TestCase):
    def test_all_supplied_demo_attachments_can_be_prepared(self):
        test_data = Path(__file__).resolve().parent.parent / "test_data"
        supported = [
            path for path in test_data.iterdir()
            if path.suffix.casefold() in {".pdf", ".xlsx", ".xlsm", ".png", ".jpg", ".jpeg"}
        ]
        self.assertTrue(supported)
        for path in supported:
            with self.subTest(path=path.name):
                attachment = EmailAttachment(
                    name=path.name,
                    content_base64=base64.b64encode(path.read_bytes()).decode("ascii"),
                )
                content = build_model_content(RawEmailRequest(
                    message_id=f"attachment-test-{path.name}",
                    subject="Attachment preparation test",
                    attachments=[attachment],
                ))
                self.assertTrue(content[0]["text"])

    def test_excel_and_html_are_prepared_for_model(self):
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.append(["PO", "Ordered Qty"])
        worksheet.append(["BIS/PROC/2026/4001", 250])
        buffer = io.BytesIO()
        workbook.save(buffer)
        attachment = EmailAttachment(
            name="order.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            content_base64=base64.b64encode(buffer.getvalue()).decode("ascii"),
        )
        email = RawEmailRequest(
            message_id="raw-mail-1",
            subject="Order update",
            body_html="<table><tr><th>Status</th><td>Confirmed</td></tr></table>",
            attachments=[attachment],
        )
        text = build_model_content(email)[0]["text"]
        self.assertIn("Status | Confirmed", text)
        self.assertIn("BIS/PROC/2026/4001 | 250", text)

    def test_structured_azure_response_is_validated(self):
        email = RawEmailRequest(message_id="raw-mail-2", subject="Dispatch")
        model_response = {
            "records": [{
                "po_order": "BIS/PROC/2026/4002",
                "update_type": "dispatch",
                "po_date": None,
                "supplier": "Supplier",
                "co_packer": None,
                "material_sku": "SKU",
                "ordered": 100,
                "confirmed": 100,
                "dispatched": 100,
                "received": None,
                "produced": None,
                "required_date": None,
                "expected_dispatch_date": None,
                "expected_delivery_date": "2026-08-02",
                "production_status_note": None,
                "remarks": "Full dispatch",
                "confidence": 0.97,
            }]
        }
        with patch("app.services.extraction_service._call_azure_openai", return_value=model_response):
            records = extract_email(email)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source_email_id, "raw-mail-2")
        self.assertEqual(records[0].update_type, UpdateType.DISPATCH)
        self.assertEqual(records[0].expected_delivery_date, date(2026, 8, 2))


if __name__ == "__main__":
    unittest.main()
