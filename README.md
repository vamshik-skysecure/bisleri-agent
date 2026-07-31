# Bisleri Supplier & Co-Packer Tracker

FastAPI business runtime for the demo architecture:

`Outlook / Copilot Studio -> Power Automate -> ngrok -> FastAPI -> Azure OpenAI + Microsoft Graph -> SharePoint`

## Implemented

- Raw email ingestion with HTML-table, PDF, scanned-PDF/image, XLSX/XLSM, CSV, and text extraction
- Azure OpenAI structured extraction with one consolidated record per PO
- Exact and guarded fuzzy PO matching
- Idempotent processing by source email and PO
- Tracker upsert, conflict/low-confidence review queue, and review resolution
- Full 11-stage state machine, next action, and owner calculation
- History audit trail and real status ageing
- Exception detection and management snapshot generation
- `X-API-Key` authentication for every business endpoint
- PO lookup through a query parameter, including PO numbers containing `/`
- Live configuration/list-schema readiness check

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Public process health check |
| GET | `/ready` | Validate settings and all SharePoint internal columns |
| POST | `/ingest/email/raw` | Raw Power Automate email plus base64 attachments |
| POST | `/ingest/email` | Already-structured extraction |
| POST | `/tracker/upsert` | Create/update a tracker row |
| GET | `/tracker` | List tracker rows |
| GET | `/tracker/order?po_order=...` | Retrieve one PO, including slash-containing POs |
| GET | `/exceptions` | Calculate current exceptions |
| POST | `/report/generate` | Generate the management snapshot |
| GET | `/reviews` | List unresolved/resolved review items |
| POST | `/reviews/{item_id}/resolve` | Apply a human correction and close review |

All endpoints except `/health`, `/docs`, and `/openapi.json` require `X-API-Key`.

## Required Tracker columns

The confirmed existing internal names remain unchanged. Add the six new columns using the internal names shown below.

| Internal name | Suggested display name | Type |
|---|---|---|
| `Title` | PO/Order | Single line text; unique |
| `PODate` | PO Date | Date only |
| `Supplier` | Supplier | Single line text |
| `Co_x002d_packer` | Co-packer | Single line text |
| `Material_x002f_SKU` | Material/SKU | Single line text |
| `Ordered` | Ordered | Number |
| `Confirmed` | Confirmed | Number |
| `Dispatched` | Dispatched | Number |
| `Received` | Received | Number |
| `Produced` | Produced | Number |
| `Pending` | Pending | Number |
| `RequiredDate` | Required Date | Date only |
| `ExpectedDispatchDate` | Expected Dispatch Date | Date only |
| `ExpectedDeliveryDate` | Expected Delivery Date | Date only |
| `ProductionStatusNote` | Production Status Note | Multiple lines text |
| `Remarks` | Remarks | Multiple lines text |
| `CurrentStatus` | Current Status | Choice |
| `NextAction` | Next Action | Multiple lines text |
| `Owner` | Owner | Choice; multiple selection |

The History internal names are `Title`, `FieldChanged`, `OldValue`, `NewValue`, `SourceEmail`, `ChangedBy`, `Timestamp`.

The Review Queue internal names are `Title`, `ConflictReason`, `ExtractedData`, `Reviewed`, `ReviewedBy`, `ReviewedDate`.

## Run and test

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p "test_*.py" -v
python -m tests.run_test_harness
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs`, select **Authorize**, and enter the `API_KEY` value from `.env`.

For the complete one-time manual setup and demo sequence, see [DEMO_SETUP.md](DEMO_SETUP.md).
