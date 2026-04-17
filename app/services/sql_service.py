from sqlalchemy import text
from app import db


def run_query(sql: str) -> list[dict]:
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT"):
        raise ValueError("Only SELECT queries are permitted")

    forbidden = ("DELETE", "UPDATE", "INSERT", "DROP", "ALTER", "TRUNCATE", "EXEC")
    for keyword in forbidden:
        if keyword in sql_upper:
            raise ValueError(f"Forbidden keyword '{keyword}' in SQL")

    with db.engine.connect() as conn:
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]

    return rows
