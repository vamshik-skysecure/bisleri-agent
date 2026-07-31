"""
In-memory stand-in for SharePointClient, matching the same method signatures.
Lets us run the REAL tracker_service / matcher / status_engine / exception_engine
code against dummy documents without touching a live SharePoint tenant.
"""
import itertools


class MockSharePointClient:
    def __init__(self):
        self._store: dict[str, dict[str, dict]] = {}  # list_id -> {item_id: {"id":.., "fields":..}}
        self._counter = itertools.count(1)

    def get_items(self, list_id: str, filter_query: str | None = None, top: int = 200) -> list[dict]:
        items = list(self._store.get(list_id, {}).values())
        if filter_query and "Title eq" in filter_query:
            val = filter_query.split("'")[1]
            items = [i for i in items if i["fields"].get("Title") == val]
        return items

    def get_item_by_po(self, list_id: str, po_order: str) -> dict | None:
        items = self.get_items(list_id, filter_query=f"fields/Title eq '{po_order}'", top=1)
        return items[0] if items else None

    def get_item(self, list_id: str, item_id: str) -> dict | None:
        return self._store.get(list_id, {}).get(item_id)

    def create_item(self, list_id: str, fields: dict) -> dict:
        item_id = str(next(self._counter))
        item = {"id": item_id, "fields": fields}
        self._store.setdefault(list_id, {})[item_id] = item
        return item

    def update_item(self, list_id: str, item_id: str, fields: dict) -> dict:
        existing = self._store[list_id][item_id]
        existing["fields"].update(fields)
        return existing

    def dump(self, list_id: str) -> list[dict]:
        return list(self._store.get(list_id, {}).values())
