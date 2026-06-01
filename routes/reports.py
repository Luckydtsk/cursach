from flask import Blueprint, abort, render_template, request, g
from database import execute_query
from report_export import send_report_file
from routes.auth import roles_required, ROLE_TEACHER, ROLE_ADMIN

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

_PROJECTS_BY_DEADLINE_SELECT = """
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
"""


def _projects_deadline_order_clause(sort_mode):
    if sort_mode == 'off':
        return 'ORDER BY p.title COLLATE NOCASE ASC'
    if sort_mode == 'desc':
        return 'ORDER BY CASE WHEN p.end_date IS NULL THEN 1 ELSE 0 END, p.end_date DESC'
    return 'ORDER BY CASE WHEN p.end_date IS NULL THEN 1 ELSE 0 END, p.end_date ASC'


def _parse_sort_mode():
    sort_mode = request.args.get('sort', 'asc')
    if sort_mode not in ('asc', 'desc', 'off'):
        sort_mode = 'asc'
    return sort_mode


def _export_format():
    fmt = (request.args.get('format') or '').lower()
    if fmt not in ('xlsx', 'docx'):
        abort(400, 'Укажите format=xlsx или format=docx')
    return fmt


def _teacher_id_or_none():
    if g.current_user["role"] == ROLE_TEACHER:
        return g.current_user["id"]
    return None


def _fetch_projects_by_deadline(sort_mode, teacher_id=None):
    order_sql = _projects_deadline_order_clause(sort_mode)
    if teacher_id is not None:
        query = _PROJECTS_BY_DEADLINE_SELECT + """
            WHERE p.supervisor_id = %s
        """ + order_sql
        return execute_query(query, (teacher_id,), fetch_all=True) or []
    query = _PROJECTS_BY_DEADLINE_SELECT + order_sql
    return execute_query(query, fetch_all=True) or []


def _projects_deadline_table(projects):
    headers = [
        '№', 'Проект', 'Руководитель', 'Должность', 'Кафедра',
        'Начало', 'Окончание', 'Статус', 'Команда', 'Задачи (вып./всего)',
    ]
    rows = []
    for idx, p in enumerate(projects, start=1):
        rows.append([
            idx,
            p.get('title'),
            p.get('supervisor_name') or 'Не назначен',
            p.get('supervisor_position') or '-',
            p.get('department_name') or '-',
            p.get('start_date'),
            p.get('end_date'),
            p.get('status') or 'Не указан',
            p.get('team_count'),
            f"{p.get('completed_tasks', 0)}/{p.get('task_count', 0)}",
        ])
    return headers, rows


def _fetch_overdue_tasks(teacher_id=None):
    query = """
        SELECT
            TRIM(s.last_name || ' ' || s.first_name || ' ' || COALESCE(s.middle_name, '')) AS student_name,
            sg.name AS group_name,
            s.email,
            p.title AS project_title,
            tk.title AS task_title,
            tk.deadline,
            ts.name AS task_status,
            TRIM(t.last_name || ' ' || t.first_name || ' ' || COALESCE(t.middle_name, '')) AS supervisor_name
        FROM task tk
        JOIN project p ON tk.project_id = p.id
        JOIN task_status ts ON tk.status_id = ts.id
        JOIN project_team pt ON pt.project_id = p.id
        JOIN student s ON pt.student_id = s.id
        LEFT JOIN student_group sg ON s.student_group_id = sg.id
        LEFT JOIN teacher t ON p.supervisor_id = t.id
        WHERE tk.deadline IS NOT NULL
          AND date(tk.deadline) < date('now')
          AND ts.name != 'Выполнена'
    """
    params = ()
    if teacher_id is not None:
        query += " AND p.supervisor_id = %s"
        params = (teacher_id,)
    query += " ORDER BY tk.deadline ASC, s.last_name, s.first_name"
    return execute_query(query, params, fetch_all=True) or []


def _overdue_table(rows):
    headers = [
        'Студент', 'Группа', 'Email', 'Проект', 'Задача',
        'Дедлайн', 'Статус задачи', 'Руководитель',
    ]
    data = [
        [
            r.get('student_name'),
            r.get('group_name') or '-',
            r.get('email'),
            r.get('project_title'),
            r.get('task_title'),
            r.get('deadline'),
            r.get('task_status'),
            r.get('supervisor_name') or '-',
        ]
        for r in rows
    ]
    return headers, data


def _can_access_project(project_id):
    if not project_id:
        return False
    if g.current_user["role"] == ROLE_ADMIN:
        return True
    owned = execute_query(
        "SELECT id FROM project WHERE id = %s AND supervisor_id = %s",
        (project_id, g.current_user["id"]),
        fetch_one=True,
    )
    return bool(owned)


def _fetch_project_team(project_id):
    return execute_query(
        """
        SELECT
            s.last_name,
            s.first_name,
            s.middle_name,
            sg.name as group_name,
            sg.course,
            d.name as department_name,
            pt.role,
            pt.joined_at,
            (SELECT COUNT(*) FROM task_student ts
             JOIN task t ON ts.task_id = t.id
             WHERE ts.student_id = s.id AND t.project_id = %s) as tasks_in_project,
            s.email,
            s.phone
        FROM project_team pt
        JOIN student s ON pt.student_id = s.id
        LEFT JOIN student_group sg ON s.student_group_id = sg.id
        LEFT JOIN department d ON sg.department_id = d.id
        WHERE pt.project_id = %s
        ORDER BY pt.joined_at ASC
        """,
        (project_id, project_id),
        fetch_all=True,
    ) or []


def _project_team_table(team):
    headers = [
        '№', 'ФИО', 'Группа', 'Курс', 'Кафедра', 'Роль',
        'Дата вступления', 'Задач в проекте', 'Email', 'Телефон',
    ]
    rows = []
    for idx, m in enumerate(team, start=1):
        fio = f"{m.get('last_name', '')} {m.get('first_name', '')} {m.get('middle_name') or ''}".strip()
        rows.append([
            idx,
            fio,
            m.get('group_name') or '-',
            m.get('course') or '-',
            m.get('department_name') or '-',
            m.get('role'),
            m.get('joined_at'),
            m.get('tasks_in_project'),
            m.get('email'),
            m.get('phone') or '-',
        ])
    return headers, rows


def _fetch_activities(project_id=None, teacher_id=None, for_export=False):
    query = """
        SELECT
            af.action_type,
            af.description,
            af.created_at,
            p.title as project_title,
            t.title as task_title,
            COALESCE(
                s.last_name || ' ' || s.first_name,
                teach.last_name || ' ' || teach.first_name
            ) as actor_name,
            CASE
                WHEN af.actor_student_id IS NOT NULL THEN 'Студент'
                ELSE 'Преподаватель'
            END as actor_role
        FROM activity_feed af
        LEFT JOIN project p ON af.project_id = p.id
        LEFT JOIN task t ON af.task_id = t.id
        LEFT JOIN student s ON af.actor_student_id = s.id
        LEFT JOIN teacher teach ON af.actor_teacher_id = teach.id
    """
    params = []

    if project_id:
        query += " WHERE af.project_id = %s"
        params.append(project_id)
    elif teacher_id is not None:
        query += " WHERE p.supervisor_id = %s"
        params.append(teacher_id)

    query += " ORDER BY af.created_at DESC"
    if not project_id and not for_export:
        query += " LIMIT 50"

    return execute_query(query, tuple(params), fetch_all=True) or []


def _activity_table(activities):
    headers = ['Дата и время', 'Тип', 'Описание', 'Проект', 'Задача', 'Автор', 'Роль']
    rows = [
        [
            a.get('created_at'),
            a.get('action_type'),
            a.get('description'),
            a.get('project_title') or '-',
            a.get('task_title') or '-',
            a.get('actor_name') or 'Система',
            a.get('actor_role') or '-',
        ]
        for a in activities
    ]
    return headers, rows


def _fetch_consultations_rows():
    role = g.current_user["role"]
    student_filter = request.args.get('student_id', type=int)
    teacher_filter = request.args.get('teacher_id', type=int)

    if role == ROLE_TEACHER:
        teacher_id = g.current_user["id"]
        students_options = execute_query(
            """
            SELECT DISTINCT s.id
            FROM student s
            JOIN project_team pt ON pt.student_id = s.id
            JOIN project p ON p.id = pt.project_id AND p.supervisor_id = %s
            """,
            (teacher_id,),
            fetch_all=True,
        )
        allowed_ids = {s["id"] for s in students_options}
        if student_filter and student_filter not in allowed_ids:
            student_filter = None

        list_params = [teacher_id]
        list_sql = """
            SELECT
                c.consultation_date,
                c.duration_minutes,
                c.note,
                TRIM(s.last_name || ' ' || s.first_name || ' ' || COALESCE(s.middle_name, '')) AS student_name,
                NULL AS teacher_name
            FROM consultation c
            JOIN student s ON s.id = c.student_id
            WHERE c.teacher_id = %s
        """
        if student_filter:
            list_sql += " AND c.student_id = %s"
            list_params.append(student_filter)
        list_sql += " ORDER BY c.consultation_date DESC, c.id DESC"
        return execute_query(list_sql, tuple(list_params), fetch_all=True) or [], role

    teachers_options = execute_query("SELECT id FROM teacher", fetch_all=True) or []
    allowed_teacher_ids = {t["id"] for t in teachers_options}
    if teacher_filter and teacher_filter not in allowed_teacher_ids:
        teacher_filter = None

    list_sql = """
        SELECT
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
    return execute_query(list_sql, tuple(list_params), fetch_all=True) or [], role


def _consultations_table(rows, role):
    if role == ROLE_ADMIN:
        headers = ['Дата', 'Преподаватель', 'Студент', 'Длительность (ч)', 'Комментарий']
        data = [
            [
                r.get('consultation_date'),
                r.get('teacher_name'),
                r.get('student_name'),
                round((r.get('duration_minutes') or 0) / 60, 2),
                r.get('note') or '—',
            ]
            for r in rows
        ]
    else:
        headers = ['Дата', 'Студент', 'Длительность (ч)', 'Комментарий']
        data = [
            [
                r.get('consultation_date'),
                r.get('student_name'),
                round((r.get('duration_minutes') or 0) / 60, 2),
                r.get('note') or '—',
            ]
            for r in rows
        ]
    return headers, data


@reports_bp.route('/')
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def reports_index():
    return render_template('reports/index.html')


@reports_bp.route('/projects-by-deadline')
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def projects_by_deadline():
    sort_mode = _parse_sort_mode()
    projects = _fetch_projects_by_deadline(sort_mode, _teacher_id_or_none())

    return render_template(
        'reports/projects_by_deadline.html',
        projects=projects,
        sort_mode=sort_mode,
    )


@reports_bp.route('/projects-by-deadline/export')
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def export_projects_by_deadline():
    fmt = _export_format()
    sort_mode = _parse_sort_mode()
    projects = _fetch_projects_by_deadline(sort_mode, _teacher_id_or_none())
    headers, rows = _projects_deadline_table(projects)
    return send_report_file(
        'Проекты по срокам сдачи',
        headers,
        rows,
        'projects_by_deadline',
        fmt,
    )


@reports_bp.route('/overdue')
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def overdue_students():
    rows = _fetch_overdue_tasks(_teacher_id_or_none())
    return render_template('reports/overdue.html', rows=rows)


@reports_bp.route('/overdue/export')
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def export_overdue_students():
    fmt = _export_format()
    rows = _fetch_overdue_tasks(_teacher_id_or_none())
    headers, data = _overdue_table(rows)
    title = 'Студенты с просроченными задачами'
    if g.current_user["role"] == ROLE_TEACHER:
        title += ' (мои проекты)'
    return send_report_file(title, headers, data, 'overdue_tasks', fmt)


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


@reports_bp.route('/project-team/export')
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def export_project_team():
    fmt = _export_format()
    project_id = request.args.get('project_id', type=int)
    if not project_id or not _can_access_project(project_id):
        abort(400, 'Укажите project_id доступного проекта')

    project = execute_query(
        "SELECT title FROM project WHERE id = %s",
        (project_id,),
        fetch_one=True,
    )
    team = _fetch_project_team(project_id)
    headers, rows = _project_team_table(team)
    title = f"Состав команды: {project['title'] if project else project_id}"
    return send_report_file(title, headers, rows, f"project_team_{project_id}", fmt)


@reports_bp.route('/activity-timeline/export')
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def export_activity_timeline():
    fmt = _export_format()
    project_id = request.args.get('project_id', type=int)

    if project_id and not _can_access_project(project_id):
        abort(403)

    teacher_id = _teacher_id_or_none()
    activities = _fetch_activities(
        project_id=project_id,
        teacher_id=teacher_id if not project_id else None,
        for_export=True,
    )
    headers, rows = _activity_table(activities)
    title = 'Хронология событий'
    if project_id:
        proj = execute_query(
            "SELECT title FROM project WHERE id = %s",
            (project_id,),
            fetch_one=True,
        )
        if proj:
            title += f": {proj['title']}"
    return send_report_file(title, headers, rows, 'activity_timeline', fmt)


@reports_bp.route('/consultations/export')
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def export_consultations():
    fmt = _export_format()
    rows, role = _fetch_consultations_rows()
    headers, data = _consultations_table(rows, role)
    title = 'Консультации с студентами'
    return send_report_file(title, headers, data, 'consultations', fmt)
