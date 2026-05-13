from flask import Blueprint, render_template, g
from database import execute_query
from routes.auth import ROLE_STUDENT, ROLE_TEACHER

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    current_user = g.current_user
    user_role = current_user.get("role") if current_user else None
    is_teacher = user_role == ROLE_TEACHER
    is_student = user_role == ROLE_STUDENT
    teacher_id = current_user.get("id") if is_teacher else None
    student_id = current_user.get("id") if is_student else None

    if is_teacher:
        projects_stats = execute_query(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN ps.name = 'В работе' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN ps.name = 'Завершен' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN ps.name = 'Планирование' THEN 1 ELSE 0 END) as planning
            FROM project p
            LEFT JOIN project_status ps ON p.status_id = ps.id
            WHERE p.supervisor_id = %s
            """,
            (teacher_id,),
            fetch_one=True,
        )

        tasks_stats = execute_query(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN ts.name = 'В работе' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN ts.name = 'Выполнена' THEN 1 ELSE 0 END) as completed
            FROM task t
            LEFT JOIN task_status ts ON t.status_id = ts.id
            JOIN project p ON t.project_id = p.id
            WHERE p.supervisor_id = %s
            """,
            (teacher_id,),
            fetch_one=True,
        )

        people_stats = execute_query(
            """
            SELECT
                COUNT(DISTINCT pt.student_id) as students,
                1 as teachers
            FROM project p
            LEFT JOIN project_team pt ON pt.project_id = p.id
            WHERE p.supervisor_id = %s
            """,
            (teacher_id,),
            fetch_one=True,
        )

        activities = execute_query(
            """
            SELECT
                af.action_type,
                af.description,
                af.created_at,
                p.title as project_title,
                COALESCE(
                    s.last_name || ' ' || s.first_name,
                    t.last_name || ' ' || t.first_name
                ) as actor_name
            FROM activity_feed af
            JOIN project p ON af.project_id = p.id
            LEFT JOIN student s ON af.actor_student_id = s.id
            LEFT JOIN teacher t ON af.actor_teacher_id = t.id
            WHERE p.supervisor_id = %s
            ORDER BY af.created_at DESC
            LIMIT 5
            """,
            (teacher_id,),
            fetch_all=True,
        )

        upcoming_deadlines = execute_query(
            """
            SELECT
                p.id,
                p.title,
                p.end_date,
                ps.name as status,
                ps.color as status_color,
                t.last_name || ' ' || t.first_name as supervisor_name
            FROM project p
            LEFT JOIN project_status ps ON p.status_id = ps.id
            LEFT JOIN teacher t ON p.supervisor_id = t.id
            WHERE p.end_date >= CURRENT_DATE AND p.supervisor_id = %s
            ORDER BY p.end_date ASC
            LIMIT 5
            """,
            (teacher_id,),
            fetch_all=True,
        )
    elif is_student:
        projects_stats = execute_query(
            """
            SELECT
                COUNT(DISTINCT p.id) as total,
                SUM(CASE WHEN ps.name = 'В работе' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN ps.name = 'Завершен' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN ps.name = 'Планирование' THEN 1 ELSE 0 END) as planning
            FROM project p
            JOIN project_team pt ON pt.project_id = p.id
            LEFT JOIN project_status ps ON p.status_id = ps.id
            WHERE pt.student_id = %s
            """,
            (student_id,),
            fetch_one=True,
        )

        tasks_stats = execute_query(
            """
            SELECT
                COUNT(DISTINCT t.id) as total,
                SUM(CASE WHEN ts.name = 'В работе' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN ts.name = 'Выполнена' THEN 1 ELSE 0 END) as completed
            FROM task t
            JOIN task_student tss ON tss.task_id = t.id
            LEFT JOIN task_status ts ON t.status_id = ts.id
            WHERE tss.student_id = %s
            """,
            (student_id,),
            fetch_one=True,
        )

        people_stats = execute_query(
            """
            SELECT
                COUNT(DISTINCT pt.student_id) as students,
                COUNT(DISTINCT p.supervisor_id) as teachers
            FROM project p
            JOIN project_team own_pt ON own_pt.project_id = p.id
            LEFT JOIN project_team pt ON pt.project_id = p.id
            WHERE own_pt.student_id = %s
            """,
            (student_id,),
            fetch_one=True,
        )

        activities = execute_query(
            """
            SELECT
                af.action_type,
                af.description,
                af.created_at,
                p.title as project_title,
                COALESCE(
                    s.last_name || ' ' || s.first_name,
                    t.last_name || ' ' || t.first_name
                ) as actor_name
            FROM activity_feed af
            JOIN project p ON af.project_id = p.id
            JOIN project_team pt ON pt.project_id = p.id
            LEFT JOIN student s ON af.actor_student_id = s.id
            LEFT JOIN teacher t ON af.actor_teacher_id = t.id
            WHERE pt.student_id = %s
            ORDER BY af.created_at DESC
            LIMIT 5
            """,
            (student_id,),
            fetch_all=True,
        )

        upcoming_deadlines = execute_query(
            """
            SELECT
                t.id,
                t.title,
                t.deadline as end_date,
                ts.name as status,
                ts.color as status_color,
                p.title as project_title
            FROM task t
            JOIN task_student tss ON tss.task_id = t.id
            LEFT JOIN task_status ts ON t.status_id = ts.id
            JOIN project p ON t.project_id = p.id
            WHERE tss.student_id = %s
              AND t.deadline IS NOT NULL
              AND t.deadline >= CURRENT_DATE
            ORDER BY t.deadline ASC
            LIMIT 5
            """,
            (student_id,),
            fetch_all=True,
        )
    else:
        projects_stats = execute_query("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN ps.name = 'В работе' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN ps.name = 'Завершен' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN ps.name = 'Планирование' THEN 1 ELSE 0 END) as planning
            FROM project p
            LEFT JOIN project_status ps ON p.status_id = ps.id
        """, fetch_one=True)

        tasks_stats = execute_query("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN ts.name = 'В работе' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN ts.name = 'Выполнена' THEN 1 ELSE 0 END) as completed
            FROM task t
            LEFT JOIN task_status ts ON t.status_id = ts.id
        """, fetch_one=True)

        people_stats = execute_query("""
            SELECT 
                (SELECT COUNT(*) FROM student) as students,
                (SELECT COUNT(*) FROM teacher) as teachers
        """, fetch_one=True)

        activities = execute_query("""
            SELECT 
                af.action_type,
                af.description,
                af.created_at,
                p.title as project_title,
                COALESCE(
                    s.last_name || ' ' || s.first_name,
                    t.last_name || ' ' || t.first_name
                ) as actor_name
            FROM activity_feed af
            LEFT JOIN project p ON af.project_id = p.id
            LEFT JOIN student s ON af.actor_student_id = s.id
            LEFT JOIN teacher t ON af.actor_teacher_id = t.id
            ORDER BY af.created_at DESC
            LIMIT 5
        """, fetch_all=True)

        upcoming_deadlines = execute_query("""
            SELECT 
                p.id,
                p.title,
                p.end_date,
                ps.name as status,
                ps.color as status_color,
                t.last_name || ' ' || t.first_name as supervisor_name
            FROM project p
            LEFT JOIN project_status ps ON p.status_id = ps.id
            LEFT JOIN teacher t ON p.supervisor_id = t.id
            WHERE p.end_date >= CURRENT_DATE
            ORDER BY p.end_date ASC
            LIMIT 5
        """, fetch_all=True)
    
    return render_template('index.html',
                         projects_stats=projects_stats,
                         tasks_stats=tasks_stats,
                         people_stats=people_stats,
                         activities=activities,
                         upcoming_deadlines=upcoming_deadlines,
                         is_student_dashboard=is_student)
