from datetime import date

from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from database import execute_query, log_activity
from routes.auth import roles_required, is_self_student, ROLE_TEACHER, ROLE_ADMIN

students_bp = Blueprint('students', __name__, url_prefix='/students')


def teacher_supervises_student(teacher_id, student_id):
    row = execute_query(
        """
        SELECT 1 AS ok
        FROM project_team pt
        JOIN project p ON p.id = pt.project_id
        WHERE pt.student_id = %s AND p.supervisor_id = %s
        LIMIT 1
        """,
        (student_id, teacher_id),
        fetch_one=True,
    )
    return bool(row)


def _first_supervised_project_id(teacher_id, student_id):
    row = execute_query(
        """
        SELECT p.id
        FROM project_team pt
        JOIN project p ON p.id = pt.project_id
        WHERE pt.student_id = %s AND p.supervisor_id = %s
        ORDER BY p.id
        LIMIT 1
        """,
        (student_id, teacher_id),
        fetch_one=True,
    )
    return row["id"] if row else None


@students_bp.route('/')
@roles_required(ROLE_ADMIN)
def list_students():
    students = execute_query("""
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
            (SELECT COUNT(*) FROM project_team pt WHERE pt.student_id = s.id) as project_count,
            (SELECT COUNT(*) FROM task_student ts WHERE ts.student_id = s.id) as task_count
        FROM student s
        LEFT JOIN student_group sg ON s.student_group_id = sg.id
        LEFT JOIN department d ON sg.department_id = d.id
        ORDER BY s.last_name, s.first_name
    """, fetch_all=True)
    
    return render_template('students/list.html', students=students)


@students_bp.route('/create', methods=['GET', 'POST'])
@roles_required(ROLE_ADMIN)
def create_student():
    if request.method == 'POST':
        last_name = request.form.get('last_name')
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        student_group_id = request.form.get('student_group_id')
        
        if not all([last_name, first_name, email]):
            flash('Заполните обязательные поля', 'error')
            return redirect(url_for('students.create_student'))
        
        try:
            execute_query("""
                INSERT INTO student (last_name, first_name, middle_name, email, phone, student_group_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (last_name, first_name, middle_name or None, email, phone or None,
                  student_group_id if student_group_id else None), commit=True)
            
            flash('Студент добавлен', 'success')
            return redirect(url_for('students.list_students'))
        except Exception as e:
            flash(f'Ошибка: email уже существует', 'error')
            return redirect(url_for('students.create_student'))
    
    groups = execute_query("""
        SELECT id, name, course FROM student_group ORDER BY name
    """, fetch_all=True)
    
    return render_template('students/create.html', groups=groups)


@students_bp.route('/supervised')
@roles_required(ROLE_TEACHER)
def supervised_students_list():
    tid = g.current_user["id"]
    students = execute_query(
        """
        SELECT DISTINCT
            s.id,
            s.last_name,
            s.first_name,
            s.middle_name,
            s.email,
            sg.name AS group_name,
            sg.course,
            (
                SELECT COUNT(DISTINCT p2.id)
                FROM project_team pt2
                JOIN project p2 ON p2.id = pt2.project_id
                WHERE pt2.student_id = s.id AND p2.supervisor_id = %s
            ) AS projects_with_me
        FROM student s
        JOIN project_team pt ON pt.student_id = s.id
        JOIN project p ON p.id = pt.project_id AND p.supervisor_id = %s
        LEFT JOIN student_group sg ON s.student_group_id = sg.id
        ORDER BY s.last_name, s.first_name
        """,
        (tid, tid),
        fetch_all=True,
    )
    return render_template('students/supervised_list.html', students=students or [])


@students_bp.route('/<int:student_id>')
def view_student(student_id):
    if not is_self_student(student_id):
        current_role = g.current_user["role"] if g.current_user else None
        if current_role not in {ROLE_TEACHER, ROLE_ADMIN}:
            flash('Недостаточно прав для просмотра профиля', 'error')
            return redirect(url_for('main.index'))

    student = execute_query("""
        SELECT 
            s.*,
            sg.name as group_name,
            sg.course,
            d.name as department_name
        FROM student s
        LEFT JOIN student_group sg ON s.student_group_id = sg.id
        LEFT JOIN department d ON sg.department_id = d.id
        WHERE s.id = %s
    """, (student_id,), fetch_one=True)
    
    if not student:
        flash('Студент не найден', 'error')
        if g.current_user and g.current_user.get('role') == ROLE_ADMIN:
            return redirect(url_for('students.list_students'))
        return redirect(url_for('main.index'))
    
    projects = execute_query("""
        SELECT 
            p.id,
            p.title,
            p.end_date,
            ps.name as status,
            ps.color as status_color,
            pt.role,
            pt.joined_at
        FROM project_team pt
        JOIN project p ON pt.project_id = p.id
        LEFT JOIN project_status ps ON p.status_id = ps.id
        WHERE pt.student_id = %s
        ORDER BY p.end_date
    """, (student_id,), fetch_all=True)
    
    tasks = execute_query("""
        SELECT 
            t.id,
            t.title,
            t.deadline,
            t.priority,
            ts.name as status,
            ts.color as status_color,
            p.title as project_title
        FROM task_student tst
        JOIN task t ON tst.task_id = t.id
        LEFT JOIN task_status ts ON t.status_id = ts.id
        LEFT JOIN project p ON t.project_id = p.id
        WHERE tst.student_id = %s
        ORDER BY t.deadline
    """, (student_id,), fetch_all=True)

    current = g.current_user
    role = current.get("role") if current else None
    teacher_can_consult = (
        role == ROLE_TEACHER
        and current.get("id")
        and teacher_supervises_student(current["id"], student_id)
    )
    consultations_teacher = []
    consultations_student_view = []
    if teacher_can_consult:
        consultations_teacher = execute_query(
            """
            SELECT c.id, c.consultation_date, c.duration_minutes, c.note, c.created_at
            FROM consultation c
            WHERE c.teacher_id = %s AND c.student_id = %s
            ORDER BY c.consultation_date DESC, c.id DESC
            """,
            (current["id"], student_id),
            fetch_all=True,
        )
    elif is_self_student(student_id):
        consultations_student_view = execute_query(
            """
            SELECT c.consultation_date, c.duration_minutes, c.note,
                   t.last_name || ' ' || t.first_name || ' ' || COALESCE(t.middle_name, '') AS teacher_name
            FROM consultation c
            JOIN teacher t ON t.id = c.teacher_id
            WHERE c.student_id = %s
            ORDER BY c.consultation_date DESC, c.id DESC
            """,
            (student_id,),
            fetch_all=True,
        )

    return render_template(
        'students/view.html',
        student=student,
        projects=projects,
        tasks=tasks,
        teacher_can_consult=teacher_can_consult,
        consultations_teacher=consultations_teacher,
        consultations_student_view=consultations_student_view,
    )


@students_bp.route('/<int:student_id>/consultations', methods=['POST'])
@roles_required(ROLE_TEACHER)
def add_consultation(student_id):
    teacher_id = g.current_user.get('id')
    if not teacher_id or not teacher_supervises_student(teacher_id, student_id):
        flash('Можно отмечать консультации только со студентами из ваших проектов', 'error')
        return redirect(url_for('main.index'))

    student = execute_query(
        "SELECT id, last_name, first_name FROM student WHERE id = %s",
        (student_id,),
        fetch_one=True,
    )
    if not student:
        flash('Студент не найден', 'error')
        return redirect(url_for('main.index'))

    raw_date = (request.form.get('consultation_date') or '').strip()
    duration_hours_raw = (request.form.get('duration_hours') or '').strip().replace(',', '.')
    note = (request.form.get('note') or '').strip() or None

    if not raw_date or not duration_hours_raw:
        flash('Укажите дату и длительность консультации', 'error')
        return redirect(url_for('students.view_student', student_id=student_id))

    try:
        date.fromisoformat(raw_date)
    except ValueError:
        flash('Некорректная дата', 'error')
        return redirect(url_for('students.view_student', student_id=student_id))

    try:
        duration_hours = float(duration_hours_raw)
    except ValueError:
        flash('Некорректная длительность (часы)', 'error')
        return redirect(url_for('students.view_student', student_id=student_id))

    if duration_hours <= 0:
        flash('Длительность должна быть больше нуля', 'error')
        return redirect(url_for('students.view_student', student_id=student_id))

    duration_minutes = max(1, int(round(duration_hours * 60)))

    execute_query(
        """
        INSERT INTO consultation (teacher_id, student_id, consultation_date, duration_minutes, note)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (teacher_id, student_id, raw_date, duration_minutes, note),
        commit=True,
    )

    project_id = _first_supervised_project_id(teacher_id, student_id)
    student_label = f"{student['last_name']} {student['first_name']}".strip()
    log_activity(
        'consultation_logged',
        f'Консультация со студентом {student_label}, {duration_hours_raw} ч.',
        current_user=g.current_user,
        project_id=project_id,
        task_id=None,
    )
    flash('Консультация сохранена', 'success')
    return redirect(url_for('students.view_student', student_id=student_id))


@students_bp.route('/<int:student_id>/edit', methods=['GET', 'POST'])
@roles_required(ROLE_ADMIN)
def edit_student(student_id):
    if request.method == 'POST':
        last_name = request.form.get('last_name')
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        student_group_id = request.form.get('student_group_id')
        
        execute_query("""
            UPDATE student 
            SET last_name = %s, first_name = %s, middle_name = %s, 
                email = %s, phone = %s, student_group_id = %s
            WHERE id = %s
        """, (last_name, first_name, middle_name or None, email, phone or None,
              student_group_id if student_group_id else None, student_id), commit=True)
        
        flash('Данные обновлены', 'success')
        return redirect(url_for('students.view_student', student_id=student_id))
    
    student = execute_query("SELECT * FROM student WHERE id = %s", (student_id,), fetch_one=True)
    groups = execute_query("SELECT id, name, course FROM student_group ORDER BY name", fetch_all=True)
    
    return render_template('students/edit.html', student=student, groups=groups)


@students_bp.route('/<int:student_id>/delete', methods=['POST'])
@roles_required(ROLE_ADMIN)
def delete_student(student_id):
    execute_query("DELETE FROM student WHERE id = %s", (student_id,), commit=True)
    flash('Студент удален', 'success')
    return redirect(url_for('students.list_students'))
