import os
from uuid import uuid4

from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, g
from werkzeug.utils import secure_filename

from database import execute_query, log_activity
from routes.auth import (
    roles_required,
    ROLE_STUDENT,
    ROLE_TEACHER,
    ROLE_ADMIN,
    can_manage_project,
    can_manage_task,
    can_update_task_status,
)

tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')


def _can_submit_to_task(task_id, student_id):
    """Участник команды проекта может сдавать файлы по любой задаче этого проекта (как по самому проекту)."""
    task = execute_query(
        "SELECT project_id FROM task WHERE id = %s",
        (task_id,),
        fetch_one=True,
    )
    if not task:
        return False
    membership = execute_query(
        """
        SELECT id FROM project_team
        WHERE project_id = %s AND student_id = %s
        """,
        (task["project_id"], student_id),
        fetch_one=True,
    )
    return bool(membership)


@tasks_bp.route('/')
def list_tasks():
    if g.current_user["role"] == ROLE_TEACHER:
        tasks = execute_query("""
            SELECT 
                t.id,
                t.title,
                t.description,
                t.deadline,
                t.priority,
                ts.name as status,
                ts.color as status_color,
                p.id as project_id,
                p.title as project_title,
                (SELECT GROUP_CONCAT(s.last_name || ' ' || SUBSTR(s.first_name, 1, 1) || '.', ', ')
                 FROM task_student ts2 
                 JOIN student s ON ts2.student_id = s.id 
                 WHERE ts2.task_id = t.id) as assignees
            FROM task t
            LEFT JOIN task_status ts ON t.status_id = ts.id
            LEFT JOIN project p ON t.project_id = p.id
            WHERE p.supervisor_id = %s
            ORDER BY t.priority DESC, t.deadline ASC
        """, (g.current_user["id"],), fetch_all=True)
    elif g.current_user["role"] == ROLE_STUDENT:
        tasks = execute_query("""
            SELECT 
                t.id,
                t.title,
                t.description,
                t.deadline,
                t.priority,
                ts.name as status,
                ts.color as status_color,
                p.id as project_id,
                p.title as project_title,
                (SELECT GROUP_CONCAT(s.last_name || ' ' || SUBSTR(s.first_name, 1, 1) || '.', ', ')
                 FROM task_student ts2 
                 JOIN student s ON ts2.student_id = s.id 
                 WHERE ts2.task_id = t.id) as assignees
            FROM task t
            LEFT JOIN task_status ts ON t.status_id = ts.id
            LEFT JOIN project p ON t.project_id = p.id
            JOIN project_team pt_own ON pt_own.project_id = p.id
            WHERE pt_own.student_id = %s
            ORDER BY t.priority DESC, t.deadline ASC
        """, (g.current_user["id"],), fetch_all=True)
    else:
        tasks = execute_query("""
            SELECT 
                t.id,
                t.title,
                t.description,
                t.deadline,
                t.priority,
                ts.name as status,
                ts.color as status_color,
                p.id as project_id,
                p.title as project_title,
                (SELECT GROUP_CONCAT(s.last_name || ' ' || SUBSTR(s.first_name, 1, 1) || '.', ', ')
                 FROM task_student ts2 
                 JOIN student s ON ts2.student_id = s.id 
                 WHERE ts2.task_id = t.id) as assignees
            FROM task t
            LEFT JOIN task_status ts ON t.status_id = ts.id
            LEFT JOIN project p ON t.project_id = p.id
            ORDER BY t.priority DESC, t.deadline ASC
        """, fetch_all=True)
    
    for task in tasks:
        task["can_edit"] = can_manage_task(task["id"])

    return render_template('tasks/list.html', tasks=tasks)


@tasks_bp.route('/create', methods=['GET', 'POST'])
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def create_task():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        project_id = request.form.get('project_id')
        status_id = request.form.get('status_id')
        priority = request.form.get('priority', 1)
        deadline = request.form.get('deadline')

        if project_id and not can_manage_project(int(project_id)):
            flash('Вы можете создавать задачи только в своих проектах', 'error')
            return redirect(url_for('tasks.list_tasks'))
        
        if not all([title, project_id]):
            flash('Заполните обязательные поля', 'error')
            return redirect(url_for('tasks.create_task'))
        
        created_task = execute_query("""
            INSERT INTO task (title, description, project_id, status_id, priority, deadline)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (title, description, project_id, 
              status_id if status_id else 1,
              priority, 
              deadline if deadline else None), commit=True)
        log_activity(
            "task_created",
            f"Создана задача: {title}",
            current_user=g.current_user,
            project_id=int(project_id),
            task_id=created_task["id"] if created_task else None,
        )
        
        flash('Задача успешно создана', 'success')
        return redirect(url_for('tasks.list_tasks'))
    
    selected_project_id = request.args.get('project_id', type=int)
    if g.current_user["role"] == ROLE_TEACHER:
        projects = execute_query(
            "SELECT id, title FROM project WHERE supervisor_id = %s ORDER BY title",
            (g.current_user["id"],),
            fetch_all=True
        )
    else:
        projects = execute_query("SELECT id, title FROM project ORDER BY title", fetch_all=True)

    if selected_project_id and not can_manage_project(selected_project_id):
        selected_project_id = None

    statuses = execute_query("SELECT id, name FROM task_status ORDER BY id", fetch_all=True)
    
    return render_template(
        'tasks/create.html',
        projects=projects,
        statuses=statuses,
        selected_project_id=selected_project_id
    )


@tasks_bp.route('/<int:task_id>')
def view_task(task_id):
    task = execute_query("""
        SELECT 
            t.*,
            ts.name as status,
            ts.color as status_color,
            p.id as project_id,
            p.title as project_title
        FROM task t
        LEFT JOIN task_status ts ON t.status_id = ts.id
        LEFT JOIN project p ON t.project_id = p.id
        WHERE t.id = %s
    """, (task_id,), fetch_one=True)
    
    if not task:
        flash('Задача не найдена', 'error')
        return redirect(url_for('tasks.list_tasks'))

    if g.current_user["role"] == ROLE_STUDENT:
        project_access = execute_query(
            """
            SELECT id
            FROM project_team
            WHERE project_id = %s AND student_id = %s
            """,
            (task["project_id"], g.current_user["id"]),
            fetch_one=True
        )
        if not project_access:
            flash('Студент может просматривать только задачи своих проектов', 'error')
            return redirect(url_for('tasks.list_tasks'))
    
    can_edit_task = can_manage_task(task_id)
    can_change_status = can_update_task_status(task_id)

    assignees = execute_query("""
        SELECT 
            s.id,
            s.last_name || ' ' || s.first_name as student_name,
            s.email,
            sg.name as group_name,
            ts.assigned_at
        FROM task_student ts
        JOIN student s ON ts.student_id = s.id
        LEFT JOIN student_group sg ON s.student_group_id = sg.id
        WHERE ts.task_id = %s
        ORDER BY ts.assigned_at
    """, (task_id,), fetch_all=True)
    
    available_students = execute_query("""
        SELECT s.id, s.last_name || ' ' || s.first_name as full_name
        FROM project_team pt
        JOIN student s ON pt.student_id = s.id
        WHERE pt.project_id = %s
        AND s.id NOT IN (SELECT student_id FROM task_student WHERE task_id = %s)
        ORDER BY s.last_name
    """, (task['project_id'], task_id), fetch_all=True)

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
        WHERE f.task_id = %s
        ORDER BY f.uploaded_at DESC
        """,
        (task_id,),
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
        WHERE c.task_id = %s
        ORDER BY c.created_at DESC
        """,
        (task_id,),
        fetch_all=True,
    )
    
    return render_template(
        'tasks/view.html',
        task=task,
        assignees=assignees,
        available_students=available_students,
        can_edit_task=can_edit_task,
        can_change_status=can_change_status,
        submissions=submissions,
        teacher_comments=teacher_comments,
        can_submit=g.current_user["role"] == ROLE_STUDENT and _can_submit_to_task(task_id, g.current_user["id"]),
        can_comment=g.current_user["role"] in {ROLE_TEACHER, ROLE_ADMIN} and can_manage_task(task_id),
    )


@tasks_bp.route('/<int:task_id>/edit', methods=['GET', 'POST'])
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def edit_task(task_id):
    if not can_manage_task(task_id):
        flash('Вы можете редактировать только задачи своих проектов', 'error')
        return redirect(url_for('tasks.view_task', task_id=task_id))

    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        status_id = request.form.get('status_id')
        priority = request.form.get('priority')
        deadline = request.form.get('deadline')
        task = execute_query("SELECT project_id FROM task WHERE id = %s", (task_id,), fetch_one=True)
        
        execute_query("""
            UPDATE task 
            SET title = %s, description = %s, status_id = %s, priority = %s, 
                deadline = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (title, description, status_id, priority, 
              deadline if deadline else None, task_id), commit=True)
        log_activity(
            "task_updated",
            f"Обновлена задача: {title}",
            current_user=g.current_user,
            project_id=task["project_id"] if "project_id" in task else None,
            task_id=task_id,
        )
        
        flash('Задача обновлена', 'success')
        return redirect(url_for('tasks.view_task', task_id=task_id))
    
    task = execute_query("SELECT * FROM task WHERE id = %s", (task_id,), fetch_one=True)
    statuses = execute_query("SELECT id, name FROM task_status ORDER BY id", fetch_all=True)
    
    return render_template('tasks/edit.html', task=task, statuses=statuses)


@tasks_bp.route('/<int:task_id>/delete', methods=['POST'])
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def delete_task(task_id):
    if not can_manage_task(task_id):
        flash('Вы можете удалять только задачи своих проектов', 'error')
        return redirect(url_for('tasks.view_task', task_id=task_id))

    task = execute_query(
        "SELECT title, project_id FROM task WHERE id = %s",
        (task_id,),
        fetch_one=True,
    )
    execute_query("DELETE FROM task WHERE id = %s", (task_id,), commit=True)
    log_activity(
        "task_deleted",
        f"Удалена задача: {task['title'] if task else task_id}",
        current_user=g.current_user,
        project_id=task["project_id"] if task else None,
        task_id=task_id,
    )
    flash('Задача удалена', 'success')
    return redirect(url_for('tasks.list_tasks'))


@tasks_bp.route('/<int:task_id>/assign', methods=['POST'])
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def assign_student(task_id):
    if not can_manage_task(task_id):
        flash('Вы можете назначать исполнителей только в своих проектах', 'error')
        return redirect(url_for('tasks.view_task', task_id=task_id))

    student_id = request.form.get('student_id')
    
    if student_id:
        try:
            execute_query("""
                INSERT INTO task_student (task_id, student_id)
                VALUES (%s, %s)
            """, (task_id, student_id), commit=True)
            task_ref = execute_query(
                "SELECT project_id FROM task WHERE id = %s",
                (task_id,),
                fetch_one=True,
            )
            student = execute_query(
                "SELECT last_name || ' ' || first_name as full_name FROM student WHERE id = %s",
                (student_id,),
                fetch_one=True,
            )
            log_activity(
                "task_assignment_updated",
                f"На задачу назначен студент: {student['full_name'] if student else student_id}",
                current_user=g.current_user,
                project_id=task_ref["project_id"] if task_ref else None,
                task_id=task_id,
            )
            flash('Исполнитель назначен', 'success')
        except Exception:
            flash('Студент уже назначен на задачу', 'error')
    
    return redirect(url_for('tasks.view_task', task_id=task_id))


@tasks_bp.route('/<int:task_id>/unassign/<int:student_id>', methods=['POST'])
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def unassign_student(task_id, student_id):
    if not can_manage_task(task_id):
        flash('Вы можете изменять исполнителей только в своих проектах', 'error')
        return redirect(url_for('tasks.view_task', task_id=task_id))

    execute_query("""
        DELETE FROM task_student WHERE task_id = %s AND student_id = %s
    """, (task_id, student_id), commit=True)
    task_ref = execute_query(
        "SELECT project_id FROM task WHERE id = %s",
        (task_id,),
        fetch_one=True,
    )
    log_activity(
        "task_assignment_updated",
        "Исполнитель снят с задачи",
        current_user=g.current_user,
        project_id=task_ref["project_id"] if task_ref else None,
        task_id=task_id,
    )
    flash('Исполнитель удален', 'success')
    return redirect(url_for('tasks.view_task', task_id=task_id))


@tasks_bp.route('/<int:task_id>/status', methods=['POST'])
@roles_required(ROLE_STUDENT, ROLE_TEACHER, ROLE_ADMIN)
def update_status(task_id):
    if not can_update_task_status(task_id):
        flash('Недостаточно прав для изменения статуса этой задачи', 'error')
        return redirect(url_for('tasks.view_task', task_id=task_id))

    status_id = request.form.get('status_id')
    
    execute_query("""
        UPDATE task SET status_id = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s
    """, (status_id, task_id), commit=True)
    task_ref = execute_query(
        """
        SELECT t.project_id, ts.name as status_name
        FROM task t
        LEFT JOIN task_status ts ON ts.id = t.status_id
        WHERE t.id = %s
        """,
        (task_id,),
        fetch_one=True,
    )
    log_activity(
        "task_status_updated",
        f"Изменен статус задачи на: {task_ref['status_name'] if task_ref and task_ref['status_name'] else 'Неизвестно'}",
        current_user=g.current_user,
        project_id=task_ref["project_id"] if task_ref else None,
        task_id=task_id,
    )
    
    flash('Статус обновлен', 'success')
    return redirect(url_for('tasks.view_task', task_id=task_id))


@tasks_bp.route('/<int:task_id>/submit', methods=['POST'])
@roles_required(ROLE_STUDENT)
def submit_task_work(task_id):
    if not _can_submit_to_task(task_id, g.current_user["id"]):
        flash('Вы можете сдавать работы только по задачам проектов, в которых вы состоите в команде', 'error')
        return redirect(url_for('tasks.view_task', task_id=task_id))

    uploaded = request.files.get('work_file')
    if not uploaded or not uploaded.filename:
        flash('Выберите файл для загрузки', 'error')
        return redirect(url_for('tasks.view_task', task_id=task_id))

    original_name = secure_filename(uploaded.filename)
    if not original_name:
        flash('Некорректное имя файла', 'error')
        return redirect(url_for('tasks.view_task', task_id=task_id))

    stored_name = f"{uuid4().hex}_{original_name}"
    full_path = os.path.join(current_app.config["UPLOAD_FOLDER"], stored_name)
    uploaded.save(full_path)
    size = os.path.getsize(full_path)

    execute_query(
        """
        INSERT INTO file (name, path, size, mime_type, task_id, uploaded_by_student_id)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (uploaded.filename, full_path, size, uploaded.mimetype, task_id, g.current_user["id"]),
        commit=True,
    )
    task_ref = execute_query("SELECT project_id FROM task WHERE id = %s", (task_id,), fetch_one=True)
    log_activity(
        "submission_uploaded",
        f"Загружена работа по задаче: {uploaded.filename}",
        current_user=g.current_user,
        project_id=task_ref["project_id"] if task_ref else None,
        task_id=task_id,
    )

    flash('Работа по задаче загружена', 'success')
    return redirect(url_for('tasks.view_task', task_id=task_id))


@tasks_bp.route('/<int:task_id>/comment', methods=['POST'])
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def add_task_comment(task_id):
    if not can_manage_task(task_id):
        flash('Вы можете комментировать только задачи своих проектов', 'error')
        return redirect(url_for('tasks.view_task', task_id=task_id))

    content = (request.form.get('content') or '').strip()
    if not content:
        flash('Введите текст комментария', 'error')
        return redirect(url_for('tasks.view_task', task_id=task_id))

    execute_query(
        """
        INSERT INTO comment (content, task_id, author_teacher_id)
        VALUES (%s, %s, %s)
        """,
        (content, task_id, g.current_user["id"]),
        commit=True,
    )
    task_ref = execute_query("SELECT project_id FROM task WHERE id = %s", (task_id,), fetch_one=True)
    log_activity(
        "comment_created",
        "Добавлен комментарий к задаче",
        current_user=g.current_user,
        project_id=task_ref["project_id"] if task_ref else None,
        task_id=task_id,
    )
    flash('Комментарий добавлен', 'success')
    return redirect(url_for('tasks.view_task', task_id=task_id))
