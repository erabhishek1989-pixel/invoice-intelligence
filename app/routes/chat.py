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

        if sql == "CANNOT_ANSWER":
            answer = "I can't answer that from the invoice data."
            sql_used = None
        else:
            results = run_query(sql)
            answer = generate_answer(question, results)
            sql_used = sql

        log = QueryLog(
            user_id=DEMO_USER_ID,
            question=question,
            sql_generated=sql_used,
            answer=answer,
            was_voice=was_voice,
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({"answer": answer, "sql": sql_used})

    except Exception as exc:
        current_app.logger.error("Query failed: %s", exc)
        return jsonify({"error": "Something went wrong. Please try again."}), 500
