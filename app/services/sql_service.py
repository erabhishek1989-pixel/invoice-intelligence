import logging
from sqlalchemy import text
from app import db

logger = logging.getLogger(__name__)

_FORBIDDEN = ("DELETE", "UPDATE", "INSERT", "DROP", "ALTER", "TRUNCATE", "EXEC", "GRANT", "REVOKE")


def run_query(sql: str) -> list[dict]:
    """Execute a GPT-generated SQL query with safety checks.

    Raises ValueError for non-SELECT or dangerous queries.
    Raises RuntimeError if the DB returns an error.
    """
    sql = sql.strip()
    sql_upper = sql.upper()

    if not sql_upper.startswith("SELECT"):
        logger.warning("Blocked non-SELECT query: %s", sql[:120])
        raise ValueError(f"Only SELECT queries are permitted (got: {sql[:80]})")

    for keyword in _FORBIDDEN:
        # word-boundary check avoids false positives like "SELECTION"
        if f" {keyword} " in f" {sql_upper} ":
            logger.warning("Blocked query with forbidden keyword %s: %s", keyword, sql[:120])
            raise ValueError(f"Forbidden keyword '{keyword}' in query")

    try:
        with db.engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
        return rows
    except Exception as exc:
        logger.error("SQL execution error: %s | query: %s", exc, sql[:200])
        raise RuntimeError(f"Database error: {exc}") from exc
