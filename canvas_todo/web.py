from __future__ import annotations

import os

from flask import Flask, jsonify, render_template

from canvas_todo import db
from canvas_todo.dateutils import utc_now, week_of

_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
_TEMPLATE_DIR = os.path.join(os.path.dirname(_PACKAGE_DIR), "templates")


def create_app(db_path: str) -> Flask:
    app = Flask(__name__, template_folder=_TEMPLATE_DIR)
    app.config["DB_PATH"] = db_path

    @app.route("/")
    def index():
        conn = db.get_connection(app.config["DB_PATH"])
        db.init_db(conn)
        wk = week_of(utc_now())
        items = db.get_items_for_week(conn, wk)

        by_course: dict[str, list] = {}
        for item in items:
            by_course.setdefault(item["course_name"], []).append(item)

        return render_template("index.html", by_course=by_course)

    @app.route("/items/<int:item_id>/toggle", methods=["POST"])
    def toggle(item_id: int):
        conn = db.get_connection(app.config["DB_PATH"])
        db.init_db(conn)
        try:
            new_status = db.toggle_item(conn, item_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"id": item_id, "status": new_status})

    return app


if __name__ == "__main__":
    app = create_app(os.environ.get("CANVAS_TODO_DB", "canvas_todo.db"))
    app.run(debug=True)
