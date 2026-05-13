import os

from flask import Blueprint, abort, g, send_from_directory

from database import execute_query
from routes.auth import (
    ROLE_ADMIN,
    ROLE_STUDENT,
    can_manage_project,
    can_manage_task,
)

submissions_bp = Blueprint("submissions", __name__, url_prefix="/submissions")


def _can_access_file(file_record):
    current_user = g.current_user
    if not current_user:
        return False

    role = current_user["role"]
    if role == ROLE_ADMIN:
        return True

    if role == ROLE_STUDENT:
        student_id = current_user.get("id")
        if file_record["project_id"]:
            membership = execute_query(
                "SELECT id FROM project_team WHERE project_id = %s AND student_id = %s",
                (file_record["project_id"], student_id),
                fetch_one=True,
            )
            return bool(membership)

        if file_record["task_id"]:
            row = execute_query(
                """
                SELECT 1 AS ok
                FROM task t
                JOIN project_team pt ON pt.project_id = t.project_id AND pt.student_id = %s
                WHERE t.id = %s
                LIMIT 1
                """,
                (student_id, file_record["task_id"]),
                fetch_one=True,
            )
            return bool(row)

        return False

    if file_record["project_id"]:
        return can_manage_project(file_record["project_id"])
    if file_record["task_id"]:
        return can_manage_task(file_record["task_id"])
    return False


@submissions_bp.route("/files/<int:file_id>/download")
def download_file(file_id):
    file_record = execute_query(
        "SELECT id, name, path, project_id, task_id FROM file WHERE id = %s",
        (file_id,),
        fetch_one=True,
    )
    if not file_record or not _can_access_file(file_record):
        abort(403)

    if not os.path.isfile(file_record["path"]):
        abort(404)

    return send_from_directory(
        os.path.dirname(file_record["path"]),
        os.path.basename(file_record["path"]),
        as_attachment=True,
        download_name=file_record["name"],
    )
