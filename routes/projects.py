import os
from uuid import uuid4

from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, g
from werkzeug.utils import secure_filename

from database import execute_query, log_activity
from datetime import date
from routes.auth import roles_required, ROLE_STUDENT, ROLE_TEACHER, ROLE_ADMIN, can_manage_project

projects_bp = Blueprint('projects', __name__, url_prefix='/projects')


def _can_submit_to_project(project_id, student_id):
    membership = execute_query(
        """
        SELECT id
        FROM project_team
        WHERE project_id = %s AND student_id = %s
        """,
        (project_id, student_id),
        fetch_one=True,
    )
    return bool(membership)


def _get_project_form_data():
    statuses = execute_query("SELECT id, name FROM project_status ORDER BY id", fetch_all=True)
    teachers = execute_query("""
        SELECT id, last_name || ' ' || first_name || ' ' || COALESCE(middle_name, '') as full_name 
        FROM teacher ORDER BY last_name
    """, fetch_all=True)
    return statuses, teachers


@projects_bp.route('/')
def list_projects():
    if g.current_user["role"] == ROLE_TEACHER:
        projects = execute_query("""
            SELECT 
                p.id,
                p.title,
                p.description,
                p.start_date,
                p.end_date,
                p.supervisor_id,
                ps.name as status,
                ps.color as status_color,
                t.last_name || ' ' || t.first_name || ' ' || COALESCE(t.middle_name, '') as supervisor_name,
                (SELECT COUNT(*) FROM project_team pt WHERE pt.project_id = p.id) as team_count,
                (SELECT COUNT(*) FROM task tk WHERE tk.project_id = p.id) as task_count
            FROM project p
            LEFT JOIN project_status ps ON p.status_id = ps.id
            LEFT JOIN teacher t ON p.supervisor_id = t.id
            WHERE p.supervisor_id = %s
            ORDER BY p.end_date ASC
        """, (g.current_user["id"],), fetch_all=True)
    elif g.current_user["role"] == ROLE_STUDENT:
        projects = execute_query("""
            SELECT 
                p.id,
                p.title,
                p.description,
                p.start_date,
                p.end_date,
                p.supervisor_id,
                ps.name as status,
                ps.color as status_color,
                t.last_name || ' ' || t.first_name || ' ' || COALESCE(t.middle_name, '') as supervisor_name,
                (SELECT COUNT(*) FROM project_team pt WHERE pt.project_id = p.id) as team_count,
                (SELECT COUNT(*) FROM task tk WHERE tk.project_id = p.id) as task_count
            FROM project p
            LEFT JOIN project_status ps ON p.status_id = ps.id
            LEFT JOIN teacher t ON p.supervisor_id = t.id
            JOIN project_team pt_own ON pt_own.project_id = p.id
            WHERE pt_own.student_id = %s
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
                p.supervisor_id,
                ps.name as status,
                ps.color as status_color,
                t.last_name || ' ' || t.first_name || ' ' || COALESCE(t.middle_name, '') as supervisor_name,
                (SELECT COUNT(*) FROM project_team pt WHERE pt.project_id = p.id) as team_count,
                (SELECT COUNT(*) FROM task tk WHERE tk.project_id = p.id) as task_count
            FROM project p
            LEFT JOIN project_status ps ON p.status_id = ps.id
            LEFT JOIN teacher t ON p.supervisor_id = t.id
            ORDER BY p.end_date ASC
        """, fetch_all=True)
    
    for project in projects:
        project["can_edit"] = can_manage_project(project["id"])

    return render_template('projects/list.html', projects=projects)


@projects_bp.route('/create', methods=['GET', 'POST'])
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def create_project():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        status_id = request.form.get('status_id')
        supervisor_id = request.form.get('supervisor_id')
        form_data = {
            'title': title,
            'description': description,
            'start_date': start_date,
            'end_date': end_date,
            'status_id': status_id,
            'supervisor_id': supervisor_id
        }
        
        if not all([title, start_date, end_date]):
            flash('Заполните обязательные поля', 'error')
            statuses, teachers = _get_project_form_data()
            return render_template(
                'projects/create.html',
                statuses=statuses,
                teachers=teachers,
                form_data=form_data,
            )

        try:
            start_date_obj = date.fromisoformat(start_date)
            end_date_obj = date.fromisoformat(end_date)
        except ValueError:
            flash('Некорректный формат даты', 'error')
            statuses, teachers = _get_project_form_data()
            return render_template(
                'projects/create.html',
                statuses=statuses,
                teachers=teachers,
                form_data=form_data,
            )

        if start_date_obj > end_date_obj:
            flash('Дата начала не может быть позже даты окончания', 'error')
            statuses, teachers = _get_project_form_data()
            return render_template(
                'projects/create.html',
                statuses=statuses,
                teachers=teachers,
                form_data=form_data,
            )
        
        if g.current_user["role"] == ROLE_TEACHER:
            supervisor_id = g.current_user["id"]

        created_project = execute_query("""
            INSERT INTO project (title, description, start_date, end_date, status_id, supervisor_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (title, description, start_date, end_date, 
              status_id if status_id else None, 
              supervisor_id if supervisor_id else None), commit=True)
        log_activity(
            "project_created",
            f"Создан проект: {title}",
            current_user=g.current_user,
            project_id=created_project["id"] if created_project else None,
        )
        
        flash('Проект успешно создан', 'success')
        return redirect(url_for('projects.list_projects'))
    
    statuses, teachers = _get_project_form_data()
    
    return render_template('projects/create.html', statuses=statuses, teachers=teachers, form_data={})


@projects_bp.route('/<int:project_id>')
def view_project(project_id):
    project = execute_query("""
        SELECT 
            p.*,
            ps.name as status,
            ps.color as status_color,
            t.last_name || ' ' || t.first_name || ' ' || COALESCE(t.middle_name, '') as supervisor_name,
            t.email as supervisor_email
        FROM project p
        LEFT JOIN project_status ps ON p.status_id = ps.id
        LEFT JOIN teacher t ON p.supervisor_id = t.id
        WHERE p.id = %s
    """, (project_id,), fetch_one=True)
    
    if not project:
        flash('Проект не найден', 'error')
        return redirect(url_for('projects.list_projects'))

    if g.current_user["role"] == ROLE_STUDENT:
        membership = execute_query(
            """
            SELECT id
            FROM project_team
            WHERE project_id = %s AND student_id = %s
            """,
            (project_id, g.current_user["id"]),
            fetch_one=True
        )
        if not membership:
            flash('Студент может просматривать только свои проекты', 'error')
            return redirect(url_for('projects.list_projects'))
    
    can_edit_project = can_manage_project(project_id)

    team = execute_query("""
        SELECT 
            s.id,
            s.last_name || ' ' || s.first_name as student_name,
            s.email,
            sg.name as group_name,
            pt.role,
            pt.joined_at
        FROM project_team pt
        JOIN student s ON pt.student_id = s.id
        LEFT JOIN student_group sg ON s.student_group_id = sg.id
        WHERE pt.project_id = %s
        ORDER BY pt.joined_at
    """, (project_id,), fetch_all=True)
    
    tasks = execute_query("""
        SELECT 
            t.id,
            t.title,
            t.deadline,
            t.priority,
            ts.name as status,
            ts.color as status_color,
            (SELECT GROUP_CONCAT(s.last_name || ' ' || SUBSTR(s.first_name, 1, 1) || '.', ', ')
             FROM task_student ts2 
             JOIN student s ON ts2.student_id = s.id 
             WHERE ts2.task_id = t.id) as assignees
        FROM task t
        LEFT JOIN task_status ts ON t.status_id = ts.id
        WHERE t.project_id = %s
        ORDER BY t.priority DESC, t.deadline ASC
    """, (project_id,), fetch_all=True)

    submissions = execute_query(
        """
        SELECT
            f.id,
            f.name,
            f.size,
            f.uploaded_at,
            s.last_name || ' ' || s.first_name AS student_name
        FROM file f
        LEFT JOIN student s ON s.id = f.uploaded_by_student_id
        WHERE f.project_id = %s
        ORDER BY f.uploaded_at DESC
        """,
        (project_id,),
        fetch_all=True,
    )

    teacher_comments = execute_query(
        """
        SELECT
            c.id,
            c.content,
            c.created_at,
            t.last_name || ' ' || t.first_name AS teacher_name
        FROM comment c
        JOIN teacher t ON t.id = c.author_teacher_id
        WHERE c.project_id = %s
        ORDER BY c.created_at DESC
        """,
        (project_id,),
        fetch_all=True,
    )

    available_students = execute_query("""
        SELECT
            s.id,
            s.last_name || ' ' || s.first_name as full_name,
            sg.name as group_name
        FROM student s
        LEFT JOIN student_group sg ON s.student_group_id = sg.id
        WHERE s.id NOT IN (
            SELECT pt.student_id
            FROM project_team pt
            WHERE pt.project_id = %s
        )
        ORDER BY s.last_name, s.first_name
    """, (project_id,), fetch_all=True)

    return render_template(
        'projects/view.html',
        project=project,
        team=team,
        tasks=tasks,
        submissions=submissions,
        teacher_comments=teacher_comments,
        available_students=available_students,
        can_edit_project=can_edit_project,
        can_submit=g.current_user["role"] == ROLE_STUDENT and _can_submit_to_project(project_id, g.current_user["id"]),
        can_comment=g.current_user["role"] in {ROLE_TEACHER, ROLE_ADMIN} and can_manage_project(project_id),
    )


@projects_bp.route('/<int:project_id>/edit', methods=['GET', 'POST'])
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def edit_project(project_id):
    if not can_manage_project(project_id):
        flash('Вы можете редактировать только свои проекты', 'error')
        return redirect(url_for('projects.view_project', project_id=project_id))

    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        status_id = request.form.get('status_id')
        supervisor_id = request.form.get('supervisor_id')

        if not all([title, start_date, end_date]):
            flash('Заполните обязательные поля', 'error')
            return redirect(url_for('projects.edit_project', project_id=project_id))

        try:
            start_date_obj = date.fromisoformat(start_date)
            end_date_obj = date.fromisoformat(end_date)
        except ValueError:
            flash('Некорректный формат даты', 'error')
            return redirect(url_for('projects.edit_project', project_id=project_id))

        if start_date_obj > end_date_obj:
            flash('Дата начала не может быть позже даты окончания', 'error')
            return redirect(url_for('projects.edit_project', project_id=project_id))

        if g.current_user["role"] == ROLE_TEACHER:
            supervisor_id = g.current_user["id"]
        
        execute_query("""
            UPDATE project 
            SET title = %s, description = %s, start_date = %s, end_date = %s, 
                status_id = %s, supervisor_id = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (title, description, start_date, end_date, 
              status_id if status_id else None,
              supervisor_id if supervisor_id else None,
              project_id), commit=True)
        log_activity(
            "project_updated",
            f"Обновлен проект: {title}",
            current_user=g.current_user,
            project_id=project_id,
        )
        
        flash('Проект обновлен', 'success')
        return redirect(url_for('projects.view_project', project_id=project_id))
    
    project = execute_query("SELECT * FROM project WHERE id = %s", (project_id,), fetch_one=True)
    statuses = execute_query("SELECT id, name FROM project_status ORDER BY id", fetch_all=True)
    teachers = execute_query("""
        SELECT id, last_name || ' ' || first_name || ' ' || COALESCE(middle_name, '') as full_name 
        FROM teacher ORDER BY last_name
    """, fetch_all=True)
    
    return render_template('projects/edit.html', project=project, statuses=statuses, teachers=teachers)


@projects_bp.route('/<int:project_id>/delete', methods=['POST'])
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def delete_project(project_id):
    if not can_manage_project(project_id):
        flash('Вы можете удалять только свои проекты', 'error')
        return redirect(url_for('projects.view_project', project_id=project_id))

    project = execute_query("SELECT title FROM project WHERE id = %s", (project_id,), fetch_one=True)
    execute_query("DELETE FROM project WHERE id = %s", (project_id,), commit=True)
    log_activity(
        "project_deleted",
        f"Удален проект: {project['title'] if project else project_id}",
        current_user=g.current_user,
    )
    flash('Проект удален', 'success')
    return redirect(url_for('projects.list_projects'))


@projects_bp.route('/<int:project_id>/add-student', methods=['POST'])
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def add_student_to_project(project_id):
    if not can_manage_project(project_id):
        flash('Вы можете изменять команду только своих проектов', 'error')
        return redirect(url_for('projects.view_project', project_id=project_id))

    student_id = request.form.get('student_id')
    role = request.form.get('role', 'Участник')
    
    if student_id:
        try:
            execute_query("""
                INSERT INTO project_team (project_id, student_id, role)
                VALUES (%s, %s, %s)
            """, (project_id, student_id, role), commit=True)
            student = execute_query(
                "SELECT last_name || ' ' || first_name as full_name FROM student WHERE id = %s",
                (student_id,),
                fetch_one=True,
            )
            log_activity(
                "project_team_updated",
                f"В проект добавлен студент: {student['full_name'] if student else student_id}",
                current_user=g.current_user,
                project_id=project_id,
            )
            flash('Студент добавлен в команду', 'success')
        except Exception as e:
            flash('Студент уже в команде проекта', 'error')
    
    return redirect(url_for('projects.view_project', project_id=project_id))


@projects_bp.route('/<int:project_id>/remove-student/<int:student_id>', methods=['POST'])
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def remove_student_from_project(project_id, student_id):
    if not can_manage_project(project_id):
        flash('Вы можете изменять команду только своих проектов', 'error')
        return redirect(url_for('projects.view_project', project_id=project_id))

    execute_query("""
        DELETE FROM task_student
        WHERE student_id = %s
          AND task_id IN (
              SELECT id
              FROM task
              WHERE project_id = %s
          )
    """, (student_id, project_id), commit=True)

    execute_query("""
        DELETE FROM project_team WHERE project_id = %s AND student_id = %s
    """, (project_id, student_id), commit=True)
    log_activity(
        "project_team_updated",
        "Студент удален из команды проекта",
        current_user=g.current_user,
        project_id=project_id,
    )
    flash('Студент удален из команды и снят с задач проекта', 'success')
    return redirect(url_for('projects.view_project', project_id=project_id))


@projects_bp.route('/<int:project_id>/submit', methods=['POST'])
@roles_required(ROLE_STUDENT)
def submit_project_work(project_id):
    if not _can_submit_to_project(project_id, g.current_user["id"]):
        flash('Вы можете сдавать работы только в своих проектах', 'error')
        return redirect(url_for('projects.view_project', project_id=project_id))

    uploaded = request.files.get('work_file')
    if not uploaded or not uploaded.filename:
        flash('Выберите файл для загрузки', 'error')
        return redirect(url_for('projects.view_project', project_id=project_id))

    original_name = secure_filename(uploaded.filename)
    if not original_name:
        flash('Некорректное имя файла', 'error')
        return redirect(url_for('projects.view_project', project_id=project_id))

    stored_name = f"{uuid4().hex}_{original_name}"
    full_path = os.path.join(current_app.config["UPLOAD_FOLDER"], stored_name)
    uploaded.save(full_path)
    size = os.path.getsize(full_path)

    execute_query(
        """
        INSERT INTO file (name, path, size, mime_type, project_id, uploaded_by_student_id)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (uploaded.filename, full_path, size, uploaded.mimetype, project_id, g.current_user["id"]),
        commit=True,
    )
    log_activity(
        "submission_uploaded",
        f"Загружена работа по проекту: {uploaded.filename}",
        current_user=g.current_user,
        project_id=project_id,
    )

    flash('Работа успешно загружена', 'success')
    return redirect(url_for('projects.view_project', project_id=project_id))


@projects_bp.route('/<int:project_id>/comment', methods=['POST'])
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def add_project_comment(project_id):
    if not can_manage_project(project_id):
        flash('Вы можете комментировать только свои проекты', 'error')
        return redirect(url_for('projects.view_project', project_id=project_id))

    content = (request.form.get('content') or '').strip()
    if not content:
        flash('Введите текст комментария', 'error')
        return redirect(url_for('projects.view_project', project_id=project_id))

    execute_query(
        """
        INSERT INTO comment (content, project_id, author_teacher_id)
        VALUES (%s, %s, %s)
        """,
        (content, project_id, g.current_user["id"]),
        commit=True,
    )
    log_activity(
        "comment_created",
        "Добавлен комментарий к проекту",
        current_user=g.current_user,
        project_id=project_id,
    )
    flash('Комментарий добавлен', 'success')
    return redirect(url_for('projects.view_project', project_id=project_id))
