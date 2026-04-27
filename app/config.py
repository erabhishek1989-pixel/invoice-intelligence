import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()


def _build_db_url(url):
    """Convert mssql+pyodbc:// URL to odbc_connect format.
    Handles special characters (like @) in passwords and sets a generous timeout.
    """
    if not url or not url.startswith("mssql+pyodbc://"):
        return url or "sqlite:///invoice.db"

    rest = url[len("mssql+pyodbc://"):]
    at_idx = rest.rfind("@")
    userinfo = rest[:at_idx]
    hostinfo = rest[at_idx + 1:]

    colon_idx = userinfo.index(":")
    user = userinfo[:colon_idx]
    password = userinfo[colon_idx + 1:]

    slash_idx = hostinfo.index("/")
    server = hostinfo[:slash_idx]
    db_part = hostinfo[slash_idx + 1:]
    database = db_part.split("?")[0]

    odbc = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={user};"
        f"PWD={{{password}}};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=60;"
        "LoginTimeout=60;"
    )
    return f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc)}"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-fallback-change-in-production")
    SQLALCHEMY_DATABASE_URI = _build_db_url(os.environ.get("DATABASE_URL", "sqlite:///invoice.db"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB

    AZURE_STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    AZURE_STORAGE_CONTAINER = os.environ.get("AZURE_STORAGE_CONTAINER", "invoices")
    AZURE_DOC_INTELLIGENCE_ENDPOINT = os.environ.get("AZURE_DOC_INTELLIGENCE_ENDPOINT")
    AZURE_DOC_INTELLIGENCE_KEY = os.environ.get("AZURE_DOC_INTELLIGENCE_KEY")
    AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
    AZURE_OPENAI_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY")
    AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

    ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
