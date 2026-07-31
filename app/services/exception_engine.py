from datetime import date

from app.models.tracker import CurrentStatus, ExceptionRecord, ExceptionType, Owner, TrackerRow
from app.config import settings


def scan_exceptions(row: TrackerRow, days_in_current_status: int) -> list[ExceptionRecord]:
    exceptions: list[ExceptionRecord] = []
    today = date.today()

    if not row.po_order or not row.supplier or not row.material_sku or row.ordered <= 0:
        exceptions.append(ExceptionRecord(
            po_order=row.po_order or "UNKNOWN",
            exception_type=ExceptionType.MISSING_REQUIRED_DATA,
            severity="high",
            days_open=days_in_current_status,
            owner=[Owner.PROCUREMENT],
            recommended_action="Complete PO, supplier, material/SKU, and ordered quantity",
        ))

    if row.confirmed == 0 and row.current_status in (
        CurrentStatus.PO_ISSUED,
        CurrentStatus.SUPPLIER_CONFIRMATION_PENDING,
    ) and days_in_current_status >= settings.SLA_DAYS_CONFIRMATION:
        exceptions.append(ExceptionRecord(
            po_order=row.po_order,
            exception_type=ExceptionType.CONFIRMATION_OVERDUE,
            severity="medium",
            days_open=days_in_current_status,
            owner=[Owner.SUPPLIER, Owner.PROCUREMENT],
            recommended_action="Follow up with supplier for order confirmation",
        ))

    if row.expected_dispatch_date and today > row.expected_dispatch_date and row.dispatched == 0:
        exceptions.append(ExceptionRecord(
            po_order=row.po_order,
            exception_type=ExceptionType.DISPATCH_DELAYED,
            severity="high",
            days_open=(today - row.expected_dispatch_date).days,
            owner=[Owner.SUPPLIER, Owner.LOGISTICS],
            recommended_action="Dispatch date has passed — obtain vehicle and revised dispatch details",
        ))

    if row.ordered > 0 and 0 < row.dispatched < row.ordered:
        exceptions.append(ExceptionRecord(
            po_order=row.po_order,
            exception_type=ExceptionType.SHORT_DISPATCH,
            severity="medium",
            days_open=days_in_current_status,
            owner=[Owner.SUPPLIER],
            recommended_action=f"Confirm balance quantity {row.ordered - row.dispatched} — short dispatched",
        ))

    if row.dispatched > 0 and 0 < row.received < row.dispatched:
        exceptions.append(ExceptionRecord(
            po_order=row.po_order,
            exception_type=ExceptionType.SHORT_RECEIPT,
            severity="high",
            days_open=days_in_current_status,
            owner=[Owner.LOGISTICS, Owner.COPACKER],
            recommended_action="Reconcile in-transit shortage/damage against the dispatch note",
        ))

    if (row.dispatched > row.ordered > 0) or (row.received > row.dispatched > 0) or (
        row.received > 0 and row.produced > row.received
    ):
        exceptions.append(ExceptionRecord(
            po_order=row.po_order,
            exception_type=ExceptionType.QUANTITY_MISMATCH,
            severity="high",
            days_open=days_in_current_status,
            owner=[Owner.SUPPLY_CHAIN],
            recommended_action="Reconcile ordered, dispatched, received, and produced quantities",
        ))

    if row.received > 0 and row.produced == 0 and days_in_current_status >= settings.SLA_DAYS_PRODUCTION_START:
        exceptions.append(ExceptionRecord(
            po_order=row.po_order,
            exception_type=ExceptionType.RECEIVED_NO_PRODUCTION,
            severity="high",
            days_open=days_in_current_status,
            owner=[Owner.COPACKER, Owner.PRODUCTION],
            recommended_action="Escalate — material is on hand but production has not started",
        ))

    if row.required_date and row.current_status != CurrentStatus.ORDER_COMPLETED:
        days_to_required = (row.required_date - today).days
        if days_to_required < 0:
            exceptions.append(ExceptionRecord(
                po_order=row.po_order,
                exception_type=ExceptionType.OVERDUE_REQUIRED_DATE,
                severity="high",
                days_open=abs(days_to_required),
                owner=[Owner.SUPPLY_CHAIN, Owner.MANAGEMENT],
                recommended_action="Order is overdue against the required date — escalate immediately",
            ))
        elif days_to_required <= settings.AT_RISK_WINDOW_DAYS:
            exceptions.append(ExceptionRecord(
                po_order=row.po_order,
                exception_type=ExceptionType.AT_RISK_REQUIRED_DATE,
                severity="medium",
                days_open=days_in_current_status,
                owner=[Owner.SUPPLY_CHAIN],
                recommended_action=f"At risk — only {days_to_required} day(s) remain to the required date",
            ))

    return exceptions
