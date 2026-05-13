from flask import Blueprint, render_template, request, redirect, url_for, flash
from database import execute_query
from routes.auth import roles_required, ROLE_TEACHER, ROLE_ADMIN

teachers_bp = Blueprint('teachers', __name__, url_prefix='/teachers')


@teachers_bp.route('/')
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def list_teachers():
    teachers = execute_query("""
        SELECT 
            t.id,
            t.last_name,
            t.first_name,
            t.middle_name,
            t.email,
            t.phone,
            t.position,
            d.name as department_name,
            (SELECT COUNT(*) FROM project p WHERE p.supervisor_id = t.id) as project_count
        FROM teacher t
        LEFT JOIN department d ON t.department_id = d.id
        ORDER BY t.last_name, t.first_name
    """, fetch_all=True)
    
    return render_template('teachers/list.html', teachers=teachers)


@teachers_bp.route('/create', methods=['GET', 'POST'])
@roles_required(ROLE_ADMIN)
def create_teacher():
    if request.method == 'POST':
        last_name = request.form.get('last_name')
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        position = request.form.get('position')
        department_id = request.form.get('department_id')
        
        if not all([last_name, first_name, email]):
            flash('Заполните обязательные поля', 'error')
            return redirect(url_for('teachers.create_teacher'))
        
        try:
            execute_query("""
                INSERT INTO teacher (last_name, first_name, middle_name, email, phone, position, department_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (last_name, first_name, middle_name or None, email, phone or None, 
                  position or None, department_id if department_id else None), commit=True)
            
            flash('Преподаватель добавлен', 'success')
            return redirect(url_for('teachers.list_teachers'))
        except Exception:
            flash('Ошибка: email уже существует', 'error')
            return redirect(url_for('teachers.create_teacher'))
    
    departments = execute_query("SELECT id, name FROM department ORDER BY name", fetch_all=True)
    
    return render_template('teachers/create.html', departments=departments)


@teachers_bp.route('/<int:teacher_id>')
@roles_required(ROLE_TEACHER, ROLE_ADMIN)
def view_teacher(teacher_id):
    teacher = execute_query("""
        SELECT 
            t.*,
            d.name as department_name
        FROM teacher t
        LEFT JOIN department d ON t.department_id = d.id
        WHERE t.id = %s
    """, (teacher_id,), fetch_one=True)
    
    if not teacher:
        flash('Преподаватель не найден', 'error')
        return redirect(url_for('teachers.list_teachers'))
    
    projects = execute_query("""
        SELECT 
            p.id,
            p.title,
            p.start_date,
            p.end_date,
            ps.name as status,
            ps.color as status_color,
            (SELECT COUNT(*) FROM project_team pt WHERE pt.project_id = p.id) as team_count
        FROM project p
        LEFT JOIN project_status ps ON p.status_id = ps.id
        WHERE p.supervisor_id = %s
        ORDER BY p.end_date
    """, (teacher_id,), fetch_all=True)
    
    return render_template('teachers/view.html', teacher=teacher, projects=projects)


@teachers_bp.route('/<int:teacher_id>/edit', methods=['GET', 'POST'])
@roles_required(ROLE_ADMIN)
def edit_teacher(teacher_id):
    if request.method == 'POST':
        last_name = request.form.get('last_name')
        first_name = request.form.get('first_name')
        middle_name = request.form.get('middle_name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        position = request.form.get('position')
        department_id = request.form.get('department_id')
        
        execute_query("""
            UPDATE teacher 
            SET last_name = %s, first_name = %s, middle_name = %s, 
                email = %s, phone = %s, position = %s, department_id = %s
            WHERE id = %s
        """, (last_name, first_name, middle_name or None, email, phone or None,
              position or None, department_id if department_id else None, teacher_id), commit=True)
        
        flash('Данные обновлены', 'success')
        return redirect(url_for('teachers.view_teacher', teacher_id=teacher_id))
    
    teacher = execute_query("SELECT * FROM teacher WHERE id = %s", (teacher_id,), fetch_one=True)
    departments = execute_query("SELECT id, name FROM department ORDER BY name", fetch_all=True)
    
    return render_template('teachers/edit.html', teacher=teacher, departments=departments)


@teachers_bp.route('/<int:teacher_id>/delete', methods=['POST'])
@roles_required(ROLE_ADMIN)
def delete_teacher(teacher_id):
    execute_query("DELETE FROM teacher WHERE id = %s", (teacher_id,), commit=True)
    flash('Преподаватель удален', 'success')
    return redirect(url_for('teachers.list_teachers'))
