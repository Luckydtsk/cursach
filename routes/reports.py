from flask import Blueprint, render_template, request, g
from database import execute_query
from routes.auth import roles_required, ROLE_TEACHER, ROLE_ADMIN

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')


@reports_bp.route('/')
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def reports_index():
    return render_template('reports/index.html')


@reports_bp.route('/projects-by-deadline')
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def projects_by_deadline():
    if g.current_user["role"] == ROLE_TEACHER:
        projects = execute_query("""
            SELECT 
                p.id,
                p.title,
                p.description,
                p.start_date,
                p.end_date,
                ps.name as status,
                ps.color as status_color,
                t.last_name || ' ' || t.first_name || ' ' || COALESCE(t.middle_name, '') as supervisor_name,
                t.email as supervisor_email,
                t.position as supervisor_position,
                d.name as department_name,
                (SELECT COUNT(*) FROM project_team pt WHERE pt.project_id = p.id) as team_count,
                (SELECT COUNT(*) FROM task tk WHERE tk.project_id = p.id) as task_count,
                (SELECT COUNT(*) FROM task tk 
                 JOIN task_status ts ON tk.status_id = ts.id 
                 WHERE tk.project_id = p.id AND ts.name = 'Выполнена') as completed_tasks
            FROM project p
            LEFT JOIN project_status ps ON p.status_id = ps.id
            LEFT JOIN teacher t ON p.supervisor_id = t.id
            LEFT JOIN department d ON t.department_id = d.id
            WHERE p.supervisor_id = %s
            ORDER BY p.end_date ASC
        """, (g.current_user["id"],), fetch_all=True)
    else:
        projects = execute_query("""
            SELECT 
                p.id,
                p.title,
                p.description,
                p.start_date,
                p.end_date,
                ps.name as status,
                ps.color as status_color,
                t.last_name || ' ' || t.first_name || ' ' || COALESCE(t.middle_name, '') as supervisor_name,
                t.email as supervisor_email,
                t.position as supervisor_position,
                d.name as department_name,
                (SELECT COUNT(*) FROM project_team pt WHERE pt.project_id = p.id) as team_count,
                (SELECT COUNT(*) FROM task tk WHERE tk.project_id = p.id) as task_count,
                (SELECT COUNT(*) FROM task tk 
                 JOIN task_status ts ON tk.status_id = ts.id 
                 WHERE tk.project_id = p.id AND ts.name = 'Выполнена') as completed_tasks
            FROM project p
            LEFT JOIN project_status ps ON p.status_id = ps.id
            LEFT JOIN teacher t ON p.supervisor_id = t.id
            LEFT JOIN department d ON t.department_id = d.id
            ORDER BY p.end_date ASC
        """, fetch_all=True)
    
    return render_template('reports/projects_by_deadline.html', projects=projects)


@reports_bp.route('/project-team')
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def project_team():
    if g.current_user["role"] == ROLE_TEACHER:
        projects = execute_query(
            "SELECT id, title FROM project WHERE supervisor_id = %s ORDER BY title",
            (g.current_user["id"],),
            fetch_all=True
        )
    else:
        projects = execute_query("SELECT id, title FROM project ORDER BY title", fetch_all=True)
    
    project_id = request.args.get('project_id', type=int)
    team = None
    selected_project = None
    
    if project_id:
        if g.current_user["role"] == ROLE_TEACHER:
            owned_project = execute_query(
                "SELECT id FROM project WHERE id = %s AND supervisor_id = %s",
                (project_id, g.current_user["id"]),
                fetch_one=True
            )
            if not owned_project:
                project_id = None

    if project_id:
        selected_project = execute_query("""
            SELECT 
                p.*,
                ps.name as status,
                t.last_name || ' ' || t.first_name as supervisor_name
            FROM project p
            LEFT JOIN project_status ps ON p.status_id = ps.id
            LEFT JOIN teacher t ON p.supervisor_id = t.id
            WHERE p.id = %s
        """, (project_id,), fetch_one=True)
        
        team = execute_query("""
            SELECT 
                s.id,
                s.last_name,
                s.first_name,
                s.middle_name,
                s.email,
                s.phone,
                sg.name as group_name,
                sg.course,
                d.name as department_name,
                pt.role,
                pt.joined_at,
                (SELECT COUNT(*) FROM task_student ts 
                 JOIN task t ON ts.task_id = t.id 
                 WHERE ts.student_id = s.id AND t.project_id = %s) as tasks_in_project
            FROM project_team pt
            JOIN student s ON pt.student_id = s.id
            LEFT JOIN student_group sg ON s.student_group_id = sg.id
            LEFT JOIN department d ON sg.department_id = d.id
            WHERE pt.project_id = %s
            ORDER BY pt.joined_at ASC
        """, (project_id, project_id), fetch_all=True)
    
    return render_template('reports/project_team.html', 
                         projects=projects, 
                         team=team, 
                         selected_project=selected_project,
                         project_id=project_id)


@reports_bp.route('/activity-timeline')
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def activity_timeline():
    project_id = request.args.get('project_id', type=int)
    
    if g.current_user["role"] == ROLE_TEACHER:
        projects = execute_query(
            "SELECT id, title FROM project WHERE supervisor_id = %s ORDER BY title",
            (g.current_user["id"],),
            fetch_all=True
        )
    else:
        projects = execute_query("SELECT id, title FROM project ORDER BY title", fetch_all=True)
    
    query = """
        SELECT 
            af.id,
            af.action_type,
            af.description,
            af.created_at,
            p.id as project_id,
            p.title as project_title,
            t.title as task_title,
            COALESCE(
                s.last_name || ' ' || s.first_name,
                teach.last_name || ' ' || teach.first_name
            ) as actor_name,
            CASE 
                WHEN af.actor_student_id IS NOT NULL THEN 'student'
                ELSE 'teacher'
            END as actor_type
        FROM activity_feed af
        LEFT JOIN project p ON af.project_id = p.id
        LEFT JOIN task t ON af.task_id = t.id
        LEFT JOIN student s ON af.actor_student_id = s.id
        LEFT JOIN teacher teach ON af.actor_teacher_id = teach.id
    """
    
    if project_id:
        if g.current_user["role"] == ROLE_TEACHER:
            allowed_project = execute_query(
                "SELECT id FROM project WHERE id = %s AND supervisor_id = %s",
                (project_id, g.current_user["id"]),
                fetch_one=True
            )
            if not allowed_project:
                project_id = None

    if project_id:
        query += " WHERE af.project_id = %s"
        query += " ORDER BY af.created_at DESC"
        activities = execute_query(query, (project_id,), fetch_all=True)
    else:
        if g.current_user["role"] == ROLE_TEACHER:
            query += " WHERE p.supervisor_id = %s"
            query += " ORDER BY af.created_at DESC LIMIT 50"
            activities = execute_query(query, (g.current_user["id"],), fetch_all=True)
        else:
            query += " ORDER BY af.created_at DESC LIMIT 50"
            activities = execute_query(query, fetch_all=True)
    
    return render_template('reports/activity_timeline.html', 
                         activities=activities,
                         projects=projects,
                         project_id=project_id)


@reports_bp.route('/consultations')
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def consultations_report():
    role = g.current_user["role"]
    student_filter = request.args.get('student_id', type=int)
    teacher_filter = request.args.get('teacher_id', type=int)

    if role == ROLE_TEACHER:
        teacher_id = g.current_user["id"]
        students_options = execute_query(
            """
            SELECT DISTINCT s.id,
                   TRIM(s.last_name || ' ' || s.first_name || ' ' || COALESCE(s.middle_name, '')) AS full_name
            FROM student s
            JOIN project_team pt ON pt.student_id = s.id
            JOIN project p ON p.id = pt.project_id AND p.supervisor_id = %s
            ORDER BY s.last_name, s.first_name
            """,
            (teacher_id,),
            fetch_all=True,
        )
        allowed_ids = {s["id"] for s in (students_options or [])}
        if student_filter and student_filter not in allowed_ids:
            student_filter = None

        sum_params = [teacher_id]
        sum_sql = """
            SELECT COALESCE(SUM(c.duration_minutes), 0) AS total_minutes
            FROM consultation c
            WHERE c.teacher_id = %s
        """
        if student_filter:
            sum_sql += " AND c.student_id = %s"
            sum_params.append(student_filter)

        total_row = execute_query(sum_sql, tuple(sum_params), fetch_one=True)

        list_params = [teacher_id]
        list_sql = """
            SELECT
                c.id,
                c.consultation_date,
                c.duration_minutes,
                c.note,
                TRIM(s.last_name || ' ' || s.first_name || ' ' || COALESCE(s.middle_name, '')) AS student_name
            FROM consultation c
            JOIN student s ON s.id = c.student_id
            WHERE c.teacher_id = %s
        """
        if student_filter:
            list_sql += " AND c.student_id = %s"
            list_params.append(student_filter)
        list_sql += " ORDER BY c.consultation_date DESC, c.id DESC"
        rows = execute_query(list_sql, tuple(list_params), fetch_all=True)

        return render_template(
            'reports/consultations.html',
            role=role,
            total_minutes=total_row["total_minutes"] if total_row else 0,
            rows=rows or [],
            students_options=students_options or [],
            student_filter=student_filter,
            teachers_options=None,
            teacher_filter=None,
        )

    # Администратор: все преподаватели и студенты, фильтры по желанию
    teachers_options = execute_query(
        """
        SELECT id,
               TRIM(last_name || ' ' || first_name || ' ' || COALESCE(middle_name, '')) AS full_name
        FROM teacher
        ORDER BY last_name, first_name
        """,
        fetch_all=True,
    )
    students_options = execute_query(
        """
        SELECT id,
               TRIM(last_name || ' ' || first_name || ' ' || COALESCE(middle_name, '')) AS full_name
        FROM student
        ORDER BY last_name, first_name
        """,
        fetch_all=True,
    )

    sum_sql = """
        SELECT COALESCE(SUM(c.duration_minutes), 0) AS total_minutes
        FROM consultation c
        WHERE 1=1
    """
    sum_params = []
    if teacher_filter:
        sum_sql += " AND c.teacher_id = %s"
        sum_params.append(teacher_filter)
    if student_filter:
        sum_sql += " AND c.student_id = %s"
        sum_params.append(student_filter)

    total_row = execute_query(sum_sql, tuple(sum_params), fetch_one=True)

    list_sql = """
        SELECT
            c.id,
            c.consultation_date,
            c.duration_minutes,
            c.note,
            TRIM(s.last_name || ' ' || s.first_name || ' ' || COALESCE(s.middle_name, '')) AS student_name,
            TRIM(t.last_name || ' ' || t.first_name || ' ' || COALESCE(t.middle_name, '')) AS teacher_name
        FROM consultation c
        JOIN student s ON s.id = c.student_id
        JOIN teacher t ON t.id = c.teacher_id
        WHERE 1=1
    """
    list_params = []
    if teacher_filter:
        list_sql += " AND c.teacher_id = %s"
        list_params.append(teacher_filter)
    if student_filter:
        list_sql += " AND c.student_id = %s"
        list_params.append(student_filter)
    list_sql += " ORDER BY c.consultation_date DESC, c.id DESC"
    rows = execute_query(list_sql, tuple(list_params), fetch_all=True)

    return render_template(
        'reports/consultations.html',
        role=role,
        total_minutes=total_row["total_minutes"] if total_row else 0,
        rows=rows or [],
        students_options=students_options or [],
        student_filter=student_filter,
        teachers_options=teachers_options or [],
        teacher_filter=teacher_filter,
    )
