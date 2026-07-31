from datetime import date, datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class CurrentStatus(str, Enum):
    """Must match the Choice column options in SharePoint exactly."""
    PO_ISSUED = "PO Issued"
    SUPPLIER_CONFIRMATION_PENDING = "Supplier Confirmation Pending"
    MATERIAL_UNDER_PREPARATION = "Material Under Preparation"
    MATERIAL_DISPATCHED = "Material Dispatched"
    DELIVERED_TO_COPACKER = "Delivered to Co-packer"
    PRODUCTION_PLANNED = "Production Planned"
    PRODUCTION_IN_PROGRESS = "Production In Progress"
    FINISHED_GOODS_READY = "Finished Goods Ready"
    PARTIALLY_COMPLETED = "Partially Completed"
    DELAYED_OR_BLOCKED = "Delayed or Blocked"
    ORDER_COMPLETED = "Order Completed"


class Owner(str, Enum):
    """Choice column, multi-select allowed in SharePoint."""
    PROCUREMENT = "Procurement"
    SUPPLIER = "Supplier"
    LOGISTICS = "Logistics"
    COPACKER = "Co-packer"
    PRODUCTION = "Production"
    SUPPLY_CHAIN = "Supply Chain"
    MANAGEMENT = "Management"


class UpdateType(str, Enum):
    """Operational event identified in an email or attachment."""
    PO_ISSUED = "po_issued"
    CONFIRMATION_PENDING = "confirmation_pending"
    SUPPLIER_CONFIRMATION = "supplier_confirmation"
    MATERIAL_PREPARATION = "material_preparation"
    DISPATCH = "dispatch"
    DELIVERY = "delivery"
    PRODUCTION_PLANNED = "production_planned"
    PRODUCTION_STARTED = "production_started"
    FINISHED_GOODS_READY = "finished_goods_ready"
    PARTIAL_COMPLETION = "partial_completion"
    DELAY_OR_BLOCK = "delay_or_block"
    ORDER_COMPLETED = "order_completed"
    OTHER = "other"


class ExtractionResult(BaseModel):
    """What Copilot Studio / Azure OpenAI returns after parsing an email or attachment."""
    po_order: Optional[str] = None
    update_type: UpdateType = UpdateType.OTHER
    po_date: Optional[date] = None
    supplier: Optional[str] = None
    co_packer: Optional[str] = None
    material_sku: Optional[str] = None
    ordered: Optional[int] = Field(default=None, ge=0)
    confirmed: Optional[int] = Field(default=None, ge=0)
    dispatched: Optional[int] = Field(default=None, ge=0)
    received: Optional[int] = Field(default=None, ge=0)
    produced: Optional[int] = Field(default=None, ge=0)
    required_date: Optional[date] = None
    expected_dispatch_date: Optional[date] = None
    expected_delivery_date: Optional[date] = None
    production_status_note: Optional[str] = None
    remarks: Optional[str] = None
    source_email_id: str
    confidence: float = Field(ge=0.0, le=1.0)


class TrackerRow(BaseModel):
    """Mirrors the SharePoint tracker list columns 1:1."""
    po_order: str
    po_date: Optional[date] = None
    supplier: Optional[str] = None
    co_packer: Optional[str] = None
    material_sku: Optional[str] = None
    ordered: int = Field(default=0, ge=0)
    confirmed: int = Field(default=0, ge=0)
    dispatched: int = Field(default=0, ge=0)
    received: int = Field(default=0, ge=0)
    produced: int = Field(default=0, ge=0)
    pending: int = Field(default=0, ge=0)
    required_date: Optional[date] = None
    expected_dispatch_date: Optional[date] = None
    expected_delivery_date: Optional[date] = None
    production_status_note: Optional[str] = None
    remarks: Optional[str] = None
    current_status: CurrentStatus = CurrentStatus.PO_ISSUED
    next_action: Optional[str] = None
    owner: List[Owner] = Field(default_factory=list)
    # internal (not a SharePoint column, used for update-in-place)
    sharepoint_item_id: Optional[str] = None


class HistoryEntry(BaseModel):
    po_order: str
    field_changed: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    source_email_id: Optional[str] = None
    changed_by: str = "agent"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExceptionType(str, Enum):
    CONFIRMATION_OVERDUE = "confirmation_overdue"
    DISPATCH_DELAYED = "dispatch_delayed"
    SHORT_DISPATCH = "short_dispatch"
    SHORT_RECEIPT = "short_receipt"
    RECEIVED_NO_PRODUCTION = "received_no_production"
    AT_RISK_REQUIRED_DATE = "at_risk_required_date"
    OVERDUE_REQUIRED_DATE = "overdue_required_date"
    QUANTITY_MISMATCH = "quantity_mismatch"
    MISSING_REQUIRED_DATA = "missing_required_data"


class ExceptionRecord(BaseModel):
    po_order: str
    exception_type: ExceptionType
    severity: str  # "low" | "medium" | "high"
    days_open: int
    owner: List[Owner]
    recommended_action: str


class ReviewQueueEntry(BaseModel):
    po_order: str
    conflict_reason: str
    extraction: ExtractionResult
    existing_row: Optional[TrackerRow] = None
    reviewed: bool = False


class ReviewResolution(BaseModel):
    corrected_extraction: ExtractionResult
    reviewed_by: str


class EmailAttachment(BaseModel):
    name: str
    content_type: Optional[str] = None
    content_base64: str


class RawEmailRequest(BaseModel):
    """JSON contract designed for Power Automate's Outlook trigger."""
    message_id: str
    subject: str = ""
    sender: Optional[str] = None
    received_at: Optional[datetime] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    attachments: List[EmailAttachment] = Field(default_factory=list)
