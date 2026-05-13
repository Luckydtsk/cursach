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
