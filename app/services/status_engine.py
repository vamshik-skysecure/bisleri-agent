from datetime import date

from app.models.tracker import CurrentStatus, Owner, TrackerRow, UpdateType
from app.config import settings


def evaluate_status(
    row: TrackerRow,
    update_type: UpdateType | None = None,
    last_update: date | None = None,
) -> tuple[CurrentStatus, str, list[Owner]]:
    """Return the deterministic stage, next action, and accountable owners."""
    today = date.today()
    days_since_update = (today - last_update).days if last_update else 0
    event = update_type or UpdateType.OTHER

    # Explicit event signals take precedence where quantities alone are ambiguous.
    if event == UpdateType.ORDER_COMPLETED:
        return CurrentStatus.ORDER_COMPLETED, "None — order complete", []

    if row.current_status == CurrentStatus.ORDER_COMPLETED and event == UpdateType.OTHER:
        return CurrentStatus.ORDER_COMPLETED, "None — order complete", []

    if event == UpdateType.DELAY_OR_BLOCK or (
        row.required_date and today > row.required_date and row.current_status != CurrentStatus.ORDER_COMPLETED
    ):
        return (
            CurrentStatus.DELAYED_OR_BLOCKED,
            "Escalate delay/blocker and agree a recovery date",
            [Owner.SUPPLY_CHAIN, Owner.MANAGEMENT],
        )

    if event == UpdateType.PARTIAL_COMPLETION:
        return (
            CurrentStatus.PARTIALLY_COMPLETED,
            "Confirm whether the remaining quantity will be produced",
            [Owner.PRODUCTION, Owner.SUPPLY_CHAIN],
        )

    if event == UpdateType.FINISHED_GOODS_READY:
        return (
            CurrentStatus.FINISHED_GOODS_READY,
            "Arrange finished-goods dispatch/delivery",
            [Owner.LOGISTICS, Owner.SUPPLY_CHAIN],
        )

    if event == UpdateType.PRODUCTION_STARTED:
        return (
            CurrentStatus.PRODUCTION_IN_PROGRESS,
            "Monitor production completion",
            [Owner.PRODUCTION],
        )

    if event == UpdateType.PRODUCTION_PLANNED:
        return (
            CurrentStatus.PRODUCTION_PLANNED,
            "Start production as planned",
            [Owner.COPACKER, Owner.PRODUCTION],
        )

    if event == UpdateType.DELIVERY:
        return (
            CurrentStatus.DELIVERED_TO_COPACKER,
            "Confirm the co-packer production plan",
            [Owner.COPACKER, Owner.PRODUCTION],
        )

    if event == UpdateType.DISPATCH:
        return (
            CurrentStatus.MATERIAL_DISPATCHED,
            "Confirm delivery at the co-packer",
            [Owner.LOGISTICS],
        )

    if event in (UpdateType.SUPPLIER_CONFIRMATION, UpdateType.MATERIAL_PREPARATION):
        return (
            CurrentStatus.MATERIAL_UNDER_PREPARATION,
            "Await dispatch from the supplier",
            [Owner.SUPPLIER],
        )

    if event == UpdateType.CONFIRMATION_PENDING:
        return (
            CurrentStatus.SUPPLIER_CONFIRMATION_PENDING,
            "Follow up for supplier confirmation",
            [Owner.PROCUREMENT, Owner.SUPPLIER],
        )

    if event == UpdateType.PO_ISSUED:
        return CurrentStatus.PO_ISSUED, "Await supplier confirmation", [Owner.PROCUREMENT]

    # Quantity/note fallbacks make structured/manual updates deterministic too.
    note = (row.production_status_note or "").casefold()
    if row.current_status == CurrentStatus.FINISHED_GOODS_READY:
        return (
            CurrentStatus.FINISHED_GOODS_READY,
            "Arrange finished-goods dispatch/delivery",
            [Owner.LOGISTICS, Owner.SUPPLY_CHAIN],
        )
    if row.current_status == CurrentStatus.PARTIALLY_COMPLETED:
        return (
            CurrentStatus.PARTIALLY_COMPLETED,
            "Confirm whether the remaining quantity will be produced",
            [Owner.PRODUCTION, Owner.SUPPLY_CHAIN],
        )
    if row.ordered > 0 and row.produced >= row.ordered:
        return (
            CurrentStatus.FINISHED_GOODS_READY,
            "Arrange finished-goods dispatch/delivery",
            [Owner.LOGISTICS, Owner.SUPPLY_CHAIN],
        )
    if any(marker in note for marker in ("finished goods ready", "production completed", "completed")):
        return (
            CurrentStatus.FINISHED_GOODS_READY,
            "Arrange finished-goods dispatch/delivery",
            [Owner.LOGISTICS, Owner.SUPPLY_CHAIN],
        )
    if row.produced > 0:
        return CurrentStatus.PRODUCTION_IN_PROGRESS, "Monitor production completion", [Owner.PRODUCTION]
    if row.received > 0:
        if row.current_status == CurrentStatus.PRODUCTION_PLANNED:
            return CurrentStatus.PRODUCTION_PLANNED, "Start production as planned", [Owner.COPACKER, Owner.PRODUCTION]
        if days_since_update >= settings.SLA_DAYS_PRODUCTION_START:
            return (
                CurrentStatus.DELAYED_OR_BLOCKED,
                "Escalate — production has not started despite material on hand",
                [Owner.COPACKER, Owner.PRODUCTION],
            )
        return CurrentStatus.DELIVERED_TO_COPACKER, "Confirm the co-packer production plan", [Owner.COPACKER]
    if row.dispatched > 0:
        return CurrentStatus.MATERIAL_DISPATCHED, "Confirm delivery at the co-packer", [Owner.LOGISTICS]
    if row.confirmed > 0:
        return CurrentStatus.MATERIAL_UNDER_PREPARATION, "Await dispatch from the supplier", [Owner.SUPPLIER]
    if row.current_status == CurrentStatus.SUPPLIER_CONFIRMATION_PENDING:
        return CurrentStatus.SUPPLIER_CONFIRMATION_PENDING, "Follow up for supplier confirmation", [Owner.PROCUREMENT]
    return CurrentStatus.PO_ISSUED, "Await supplier confirmation", [Owner.PROCUREMENT]
