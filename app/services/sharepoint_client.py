"""
Thin wrapper around Microsoft Graph API for SharePoint list operations.
Auth: client-credentials flow (app-only), needs Sites.ReadWrite.All (application permission),
admin-consented in Azure AD.
"""
import time
import requests
import msal

from app.config import settings

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class SharePointClient:
    def __init__(self):
        self._app = None  # lazily created — avoids failing at import time when env vars aren't set yet
        self._token = None
        self._token_expiry = 0

    def _get_app(self) -> msal.ConfidentialClientApplication:
        if self._app is None:
            if not settings.TENANT_ID:
                raise RuntimeError("TENANT_ID not configured — set it in .env before calling SharePoint")
            self._app = msal.ConfidentialClientApplication(
                client_id=settings.CLIENT_ID,
                client_credential=settings.CLIENT_SECRET,
                authority=f"https://login.microsoftonline.com/{settings.TENANT_ID}",
            )
        return self._app

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        result = self._get_app().acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        if "access_token" not in result:
            raise RuntimeError(f"Graph auth failed: {result.get('error_description')}")
        self._token = result["access_token"]
        self._token_expiry = time.time() + result.get("expires_in", 3600)
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
            "Prefer": "HonorNonIndexedQueriesWarningMayFailRandomly",
        }

    # ---------- generic list operations ----------

    def get_items(self, list_id: str, filter_query: str | None = None, top: int = 200) -> list[dict]:
        url = f"{GRAPH_BASE}/sites/{settings.SITE_ID}/lists/{list_id}/items"
        params = {"expand": "fields", "$top": top}
        if filter_query:
            params["$filter"] = filter_query
        items = []
        while url:
            resp = requests.get(url, headers=self._headers(), params=params if "?" not in url else None)
            resp.raise_for_status()
            data = resp.json()
            items.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
            params = None
        return items

    def get_item_by_po(self, list_id: str, po_order: str) -> dict | None:
        escaped_po = po_order.replace("'", "''")
        filter_query = f"fields/Title eq '{escaped_po}'"
        items = self.get_items(list_id, filter_query=filter_query, top=1)
        return items[0] if items else None

    def get_item(self, list_id: str, item_id: str) -> dict | None:
        url = f"{GRAPH_BASE}/sites/{settings.SITE_ID}/lists/{list_id}/items/{item_id}"
        resp = requests.get(url, headers=self._headers(), params={"expand": "fields"})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_columns(self, list_id: str) -> list[dict]:
        url = f"{GRAPH_BASE}/sites/{settings.SITE_ID}/lists/{list_id}/columns"
        resp = requests.get(url, headers=self._headers(), params={"$select": "displayName,name"})
        resp.raise_for_status()
        return resp.json().get("value", [])

    def create_item(self, list_id: str, fields: dict) -> dict:
        url = f"{GRAPH_BASE}/sites/{settings.SITE_ID}/lists/{list_id}/items"
        resp = requests.post(url, headers=self._headers(), json={"fields": fields})
        resp.raise_for_status()
        return resp.json()

    def update_item(self, list_id: str, item_id: str, fields: dict) -> dict:
        url = f"{GRAPH_BASE}/sites/{settings.SITE_ID}/lists/{list_id}/items/{item_id}/fields"
        resp = requests.patch(url, headers=self._headers(), json=fields)
        resp.raise_for_status()
        return resp.json()


sharepoint_client = SharePointClient()
