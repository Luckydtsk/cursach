from functools import wraps

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from database import execute_query

ROLE_STUDENT = "student"
ROLE_TEACHER = "teacher"
ROLE_ADMIN = "admin"

ROLE_LABELS = {
    ROLE_STUDENT: "Студент",
    ROLE_TEACHER: "Преподаватель",
    ROLE_ADMIN: "Администратор",
}

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _load_users_for_login():
    students = execute_query(
        """
        SELECT id, last_name || ' ' || first_name || ' ' || COALESCE(middle_name, '') as full_name
        FROM student
        ORDER BY last_name, first_name
        """,
        fetch_all=True,
    )
    teachers = execute_query(
        """
        SELECT id, last_name || ' ' || first_name || ' ' || COALESCE(middle_name, '') as full_name
        FROM teacher
        ORDER BY last_name, first_name
        """,
        fetch_all=True,
    )
    return students, teachers


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form.get("role")
        user_id = request.form.get("user_id", type=int)

        if role not in ROLE_LABELS:
            flash("Выберите корректную роль", "error")
            return redirect(url_for("auth.login"))

        if role == ROLE_ADMIN:
            session["user"] = {
                "role": ROLE_ADMIN,
                "role_label": ROLE_LABELS[ROLE_ADMIN],
                "name": "Системный администратор",
                "id": None,
            }
            flash("Вход выполнен: Администратор", "success")
            return redirect(url_for("main.index"))

        if not user_id:
            flash("Выберите пользователя для входа", "error")
            return redirect(url_for("auth.login"))

        query = None
        if role == ROLE_STUDENT:
            query = """
                SELECT id, last_name || ' ' || first_name || ' ' || COALESCE(middle_name, '') as full_name
                FROM student
                WHERE id = %s
            """
        elif role == ROLE_TEACHER:
            query = """
                SELECT id, last_name || ' ' || first_name || ' ' || COALESCE(middle_name, '') as full_name
                FROM teacher
                WHERE id = %s
            """

        user = execute_query(query, (user_id,), fetch_one=True) if query else None
        if not user:
            flash("Пользователь не найден", "error")
            return redirect(url_for("auth.login"))

        session["user"] = {
            "role": role,
            "role_label": ROLE_LABELS[role],
            "name": user["full_name"].strip(),
            "id": user["id"],
        }
        flash(f"Вход выполнен: {ROLE_LABELS[role]}", "success")
        return redirect(url_for("main.index"))

    students, teachers = _load_users_for_login()
    return render_template("auth/login.html", students=students, teachers=teachers, roles=ROLE_LABELS)


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("user", None)
    flash("Вы вышли из системы", "success")
    return redirect(url_for("auth.login"))


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not g.current_user:
            flash("Сначала выполните вход", "error")
            return redirect(url_for("auth.login"))
        return view_func(*args, **kwargs)

    return wrapped


def roles_required(*allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            current_user = g.current_user
            if not current_user:
                flash("Сначала выполните вход", "error")
                return redirect(url_for("auth.login"))
            if current_user["role"] not in allowed_roles:
                flash("Недостаточно прав для выполнения действия", "error")
                return redirect(url_for("main.index"))
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


def is_self_student(student_id):
    current_user = g.current_user
    return (
        bool(current_user)
        and current_user["role"] == ROLE_STUDENT
        and current_user.get("id") == student_id
    )


def can_manage_project(project_id):
    current_user = g.current_user
    if not current_user:
        return False

    if current_user["role"] == ROLE_ADMIN:
        return True

    if current_user["role"] != ROLE_TEACHER:
        return False

    project = execute_query(
        "SELECT supervisor_id FROM project WHERE id = %s",
        (project_id,),
        fetch_one=True,
    )
    return bool(project and project["supervisor_id"] == current_user.get("id"))


def can_manage_task(task_id):
    task = execute_query(
        "SELECT project_id FROM task WHERE id = %s",
        (task_id,),
        fetch_one=True,
    )
    if not task:
        return False
    return can_manage_project(task["project_id"])


def can_update_task_status(task_id):
    current_user = g.current_user
    if not current_user:
        return False

    if current_user["role"] == ROLE_ADMIN:
        return True

    if current_user["role"] == ROLE_TEACHER:
        return can_manage_task(task_id)

    if current_user["role"] == ROLE_STUDENT:
        assignment = execute_query(
            """
            SELECT id
            FROM task_student
            WHERE task_id = %s AND student_id = %s
            """,
            (task_id, current_user.get("id")),
            fetch_one=True,
        )
        return bool(assignment)

    return False


def init_auth(app):
    @app.before_request
    def require_login():
        g.current_user = session.get("user")
        endpoint = request.endpoint or ""
        if endpoint.startswith("static") or endpoint.startswith("auth."):
            return None
        if not g.current_user:
            return redirect(url_for("auth.login"))
        return None

    @app.context_processor
    def inject_auth_context():
        current_user = getattr(g, "current_user", None)
        role = current_user.get("role") if current_user else None
        return {
            "current_user": current_user,
            "ROLE_STUDENT": ROLE_STUDENT,
            "ROLE_TEACHER": ROLE_TEACHER,
            "ROLE_ADMIN": ROLE_ADMIN,
            "can_manage_projects": role in {ROLE_TEACHER, ROLE_ADMIN},
            "can_manage_users": role == ROLE_ADMIN,
            "can_view_reports": role in {ROLE_TEACHER, ROLE_ADMIN},
        }
