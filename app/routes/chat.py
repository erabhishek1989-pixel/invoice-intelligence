from flask import Blueprint, render_template, request, jsonify, current_app

from app import db, DEMO_USER_ID
from app.models import QueryLog
from app.services.gpt_service import generate_sql, generate_answer
from app.services.sql_service import run_query

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/chat")
def index():
    return render_template("chat.html")


@chat_bp.route("/api/query", methods=["POST"])
def query():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    was_voice = bool(data.get("was_voice", False))

    if not question:
        return jsonify({"error": "Question is required"}), 400

    try:
        sql = generate_sql(question)
        sql_used = None

        if "CANNOT_ANSWER" in sql.upper():
            answer = "I can't answer that from the invoice data. Try asking about vendors, amounts, dates or payment status."
        else:
            try:
                results = run_query(sql)
            except ValueError as ve:
                # Bad SQL from GPT — surface cleanly, don't crash
                current_app.logger.warning("GPT produced invalid SQL: %s | %s", sql, ve)
                answer = "I couldn't generate a valid query for that question. Try rephrasing it."
                sql_used = sql
                return jsonify({"answer": answer, "sql": sql_used})

            if not results:
                answer = "No matching records found."
            else:
                answer = generate_answer(question, results)
            sql_used = sql

        # Log every query (best-effort — don't crash the response if this fails)
        try:
            log = QueryLog(
                user_id=DEMO_USER_ID,
                question=question,
                sql_generated=sql_used,
                answer=answer,
                was_voice=was_voice,
            )
            db.session.add(log)
            db.session.commit()
        except Exception as log_exc:
            current_app.logger.warning("Failed to log query: %s", log_exc)
            db.session.rollback()

        return jsonify({"answer": answer, "sql": sql_used})

    except Exception as exc:
        current_app.logger.error("Query pipeline failed: %s", exc, exc_info=True)
        return jsonify({"error": f"Something went wrong: {str(exc)[:120]}"}), 500
