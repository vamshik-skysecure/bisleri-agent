from fastapi import Depends, FastAPI
from app.config import settings
from app.routers import exceptions, ingest, report, review, tracker
from app.security import require_api_key
from app.services.field_mapping import FIELD_MAP
from app.services.sharepoint_client import sharepoint_client

app = FastAPI(
    title="Bisleri Supplier & Co-Packer Tracker API",
    description=(
        "Business logic layer for the Supplier & Co-Packer Order Tracking Agent. "
        "Exposed via OpenAPI 3.0 for consumption by Copilot Studio, Power Automate, "
        "and the Teams SDK backend, per the Skysecure Hybrid Agent Architecture."
    ),
    version="0.1.0",
)

app.include_router(tracker.router)
app.include_router(ingest.router)
app.include_router(exceptions.router)
app.include_router(report.router)
app.include_router(review.router)


@app.get("/health", summary="Health check")
def health():
    return {"status": "ok"}


@app.get("/ready", summary="Validate configuration and SharePoint schema", dependencies=[Depends(require_api_key)])
def ready():
    required_settings = {
        "TENANT_ID": settings.TENANT_ID,
        "CLIENT_ID": settings.CLIENT_ID,
        "CLIENT_SECRET": settings.CLIENT_SECRET,
        "SITE_ID": settings.SITE_ID,
        "TRACKER_LIST_ID": settings.TRACKER_LIST_ID,
        "HISTORY_LIST_ID": settings.HISTORY_LIST_ID,
        "REVIEW_LIST_ID": settings.REVIEW_LIST_ID,
        "AOAI_ENDPOINT": settings.AOAI_ENDPOINT,
        "AOAI_API_KEY": settings.AOAI_API_KEY,
        "AOAI_DEPLOYMENT": settings.AOAI_DEPLOYMENT,
    }
    missing_settings = [name for name, value in required_settings.items() if not value]
    if missing_settings:
        return {"status": "not_ready", "missing_settings": missing_settings}

    tracker_columns = {column.get("name") for column in sharepoint_client.get_columns(settings.TRACKER_LIST_ID)}
    history_columns = {column.get("name") for column in sharepoint_client.get_columns(settings.HISTORY_LIST_ID)}
    review_columns = {column.get("name") for column in sharepoint_client.get_columns(settings.REVIEW_LIST_ID)}
    expected_history = {"Title", "FieldChanged", "OldValue", "NewValue", "SourceEmail", "ChangedBy", "Timestamp"}
    expected_review = {"Title", "ConflictReason", "ExtractedData", "Reviewed", "ReviewedBy", "ReviewedDate"}
    missing_columns = {
        "Tracker": sorted(set(FIELD_MAP.values()) - tracker_columns),
        "Tracker_History": sorted(expected_history - history_columns),
        "Tracker_ReviewQueue": sorted(expected_review - review_columns),
    }
    status = "ready" if not any(missing_columns.values()) else "schema_update_required"
    return {"status": status, "missing_columns": missing_columns}

# OpenAPI spec auto-generated at /openapi.json and /docs (Swagger UI)
# -> Copilot Studio: Import > OpenAPI > paste this URL (once deployed) to auto-create tools.
