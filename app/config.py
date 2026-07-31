"""
Configuration loaded from environment variables (.env).
This is the ONLY place that should know about credentials / IDs.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- Azure AD App Registration (needs Sites.ReadWrite.All, application permission) ---
    TENANT_ID: str = os.getenv("TENANT_ID", "")
    CLIENT_ID: str = os.getenv("CLIENT_ID", "")
    CLIENT_SECRET: str = os.getenv("CLIENT_SECRET", "")

    # --- SharePoint site + lists ---
    SITE_ID: str = os.getenv("SITE_ID", "")                # from Graph: /sites/{hostname}:/sites/{sitename}
    TRACKER_LIST_ID: str = os.getenv("TRACKER_LIST_ID", "")        # main tracker list
    HISTORY_LIST_ID: str = os.getenv("HISTORY_LIST_ID", "")        # Tracker_History list
    REVIEW_LIST_ID: str = os.getenv("REVIEW_LIST_ID", "")          # Tracker_ReviewQueue list

    # --- API authentication (sent by Copilot Studio / Power Automate as X-API-Key) ---
    API_KEY: str = os.getenv("API_KEY", "")

    # --- Azure OpenAI (used for extraction; Copilot Studio calls back into this API later) ---
    AOAI_ENDPOINT: str = os.getenv("AOAI_ENDPOINT", "")
    AOAI_API_KEY: str = os.getenv("AOAI_API_KEY", "")
    AOAI_DEPLOYMENT: str = os.getenv("AOAI_DEPLOYMENT", "")
    AOAI_API_VERSION: str = os.getenv("AOAI_API_VERSION", "2024-10-21")
    AOAI_TIMEOUT_SECONDS: int = int(os.getenv("AOAI_TIMEOUT_SECONDS", 90))
    AOAI_MAX_TOKENS: int = int(os.getenv("AOAI_MAX_TOKENS", 4000))

    # --- Raw email/attachment ingestion limits ---
    MAX_ATTACHMENT_BYTES: int = int(os.getenv("MAX_ATTACHMENT_BYTES", 10 * 1024 * 1024))
    MAX_EMAIL_BYTES: int = int(os.getenv("MAX_EMAIL_BYTES", 25 * 1024 * 1024))
    MAX_EXTRACTED_TEXT_CHARS: int = int(os.getenv("MAX_EXTRACTED_TEXT_CHARS", 60000))
    MAX_PDF_PAGES: int = int(os.getenv("MAX_PDF_PAGES", 12))

    # --- Business rules (tune these with the team) ---
    SLA_DAYS_CONFIRMATION: int = int(os.getenv("SLA_DAYS_CONFIRMATION", 2))
    SLA_DAYS_DISPATCH: int = int(os.getenv("SLA_DAYS_DISPATCH", 3))
    SLA_DAYS_PRODUCTION_START: int = int(os.getenv("SLA_DAYS_PRODUCTION_START", 3))
    AT_RISK_WINDOW_DAYS: int = int(os.getenv("AT_RISK_WINDOW_DAYS", 3))
    LOW_CONFIDENCE_THRESHOLD: float = float(os.getenv("LOW_CONFIDENCE_THRESHOLD", 0.75))


settings = Settings()
