import sqlite3
from datetime import date, datetime
from config import Config


DATE_FIELDS = {"start_date", "end_date", "deadline", "joined_at", "assigned_at"}


def _parse_db_value(key, value):
    if not isinstance(value, str):
        return value

    if key.endswith("_at"):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value

    if key.endswith("_date") or key in DATE_FIELDS:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return value

    return value


def _normalize_row(row):
    raw = dict(row)
    return {key: _parse_db_value(key, value) for key, value in raw.items()}


def get_db_connection():
    conn = sqlite3.connect(Config.SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def execute_query(query, params=None, fetch_one=False, fetch_all=False, commit=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    result = None
    
    try:
        sqlite_query = query.replace("%s", "?")
        cursor.execute(sqlite_query, params or ())
        
        if fetch_one:
            row = cursor.fetchone()
            result = _normalize_row(row) if row else None
        elif fetch_all:
            result = [_normalize_row(row) for row in cursor.fetchall()]
        
        if commit:
            conn.commit()
            if cursor.description and not result:
                row = cursor.fetchone()
                result = _normalize_row(row) if row else None
            elif cursor.lastrowid and result is None:
                result = {"id": cursor.lastrowid}
                
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()
    
    return result


def log_activity(action_type, description, current_user=None, project_id=None, task_id=None):
    actor_student_id = None
    actor_teacher_id = None

    if current_user:
        role = current_user.get("role")
        user_id = current_user.get("id")
        if role == "student":
            actor_student_id = user_id
        elif role == "teacher":
            actor_teacher_id = user_id

    execute_query(
        """
        INSERT INTO activity_feed (
            action_type,
            description,
            project_id,
            task_id,
            actor_student_id,
            actor_teacher_id
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (action_type, description, project_id, task_id, actor_student_id, actor_teacher_id),
        commit=True,
    )
