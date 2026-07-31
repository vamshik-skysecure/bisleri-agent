# End-to-end demo setup

## 1. Rotate exposed credentials

Rotate the Entra client secret and Azure OpenAI key that were previously placed in the example configuration. Put only the new values in `.env`. `.env` is ignored by Git.

## 2. Add the missing Tracker columns

Create these six columns on the main Tracker list:

| Create initially with this name | Type | You may then rename the display name to |
|---|---|---|
| `PODate` | Date only | PO Date |
| `Confirmed` | Number, 0 decimal places | Confirmed |
| `ExpectedDispatchDate` | Date only | Expected Dispatch Date |
| `ExpectedDeliveryDate` | Date only | Expected Delivery Date |
| `ProductionStatusNote` | Multiple lines, plain text | Production Status Note |
| `Remarks` | Multiple lines, plain text | Remarks |

Creating them first with the compact names ensures their SharePoint internal names match the code. Renaming a display name afterward does not change its internal name.

Also verify:

- `Title` is displayed as PO/Order and enforces unique values.
- CurrentStatus has exactly the 11 choice values defined in `app/models/tracker.py`.
- Owner allows multiple selections and has exactly the seven owner values.
- ReviewedBy is single-line text and ReviewedDate is date/time on the Review Queue.

## 3. Validate `.env`

Populate all settings shown in `.env.example`. A random demo `API_KEY` is already generated in the local `.env`; use its value as the `X-API-Key` header in Copilot Studio and Power Automate.

Do not send the API key as a query parameter and do not commit `.env`.

## 4. Start locally and validate SharePoint

Terminal 1:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open Swagger at `http://127.0.0.1:8000/docs`, authorize using `API_KEY`, then call `GET /ready`.

Do not continue until it returns:

```json
{"status":"ready","missing_columns":{"Tracker":[],"Tracker_History":[],"Tracker_ReviewQueue":[]}}
```

## 5. Start ngrok

Terminal 2:

```powershell
.\ngrok.exe http 8000
```

Copy the HTTPS forwarding URL. Test `<ngrok-url>/health`. Only the health endpoint is public; business endpoints require `X-API-Key`.

If the ngrok URL changes, update the Copilot Studio and Power Automate HTTP actions.

## 6. Power Automate mailbox flow

Create an automated cloud flow:

1. Trigger: **When a new email arrives in a shared mailbox (V2)**.
2. Enable attachment inclusion and select the supplier/co-packer shared mailbox.
3. Initialize an Array variable named `AttachmentsArray`.
4. For each attachment, use **Get attachment (V2)** and append this object:

```json
{
  "name": "<attachment name dynamic value>",
  "content_type": "<attachment content type dynamic value>",
  "content_base64": "<attachment contentBytes dynamic value>"
}
```

5. Add an HTTP POST action:

```text
URL: https://<ngrok-domain>/ingest/email/raw
Headers:
  Content-Type: application/json
  X-API-Key: <API_KEY from .env>
```

6. Use this request body, replacing placeholders with Outlook dynamic values:

```json
{
  "message_id": "<Internet message ID or Outlook message ID>",
  "subject": "<Subject>",
  "sender": "<From address>",
  "received_at": "<Received time>",
  "body_html": "<Email body>",
  "attachments": "<AttachmentsArray variable>"
}
```

In the Power Automate designer, insert `AttachmentsArray` as an actual array expression, not a quoted string. The final run-history input must show `attachments: [...]`.

7. Add failure handling: when the HTTP status is not 2xx, notify the demo owner and retain the message ID for replay.

## 7. Copilot Studio HTTP topics

For each HTTP node add `X-API-Key` using the value in `.env`.

### Check one PO

```text
GET https://<ngrok-domain>/tracker/order?po_order=<URL-encoded PO variable>
```

This supports values such as `BIS/PROC/2026/1048`.

### List tracker

```text
GET https://<ngrok-domain>/tracker
```

### Show exceptions

```text
GET https://<ngrok-domain>/exceptions
```

### Generate snapshot

```text
POST https://<ngrok-domain>/report/generate
```

### Show human-review items

```text
GET https://<ngrok-domain>/reviews?reviewed=false
```

For every HTTP node, choose **From sample data** for the response type and paste a successful response captured from Swagger. Configure **Continue on error** and store both status code and error response variables.

## 8. Scheduled snapshot flow

Create a second Power Automate flow:

1. Trigger: Recurrence, daily or weekly.
2. HTTP POST `/report/generate` with `X-API-Key`.
3. Format the returned status breakdown, high-severity exceptions, and pending actions into HTML.
4. Optional: **Start and wait for an approval**.
5. Send the approved email and/or post an adaptive card to Teams.

## 9. Demo story

1. Send an acknowledgement email with an order PDF/XLSX: Tracker becomes Material Under Preparation and History is created.
2. Send dispatch advice: quantity and status update without a duplicate row.
3. Send delivery confirmation: status becomes Delivered to Co-packer.
4. Send production plan/start/completion: status progresses through Planned, In Progress, and Finished Goods Ready.
5. Send final delivery/closure: status becomes Order Completed.
6. Resend one earlier email: response shows `duplicate_ignored`.
7. Send an ambiguous or conflicting update: it enters Tracker_ReviewQueue.
8. Resolve it through `/reviews/{item_id}/resolve` and show ReviewedBy/ReviewedDate.
9. Ask Copilot for the PO, delayed orders, and the management snapshot.

Keep FastAPI, ngrok, and the laptop running during the demo. Replace ngrok with Azure App Service or Container Apps for a persistent production URL.
