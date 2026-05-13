
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS activity_feed;
DROP TABLE IF EXISTS comment;
DROP TABLE IF EXISTS file;
DROP TABLE IF EXISTS task_student;
DROP TABLE IF EXISTS task;
DROP TABLE IF EXISTS task_status;
DROP TABLE IF EXISTS project_team;
DROP TABLE IF EXISTS project;
DROP TABLE IF EXISTS project_status;
DROP TABLE IF EXISTS student;
DROP TABLE IF EXISTS student_group;
DROP TABLE IF EXISTS teacher;
DROP TABLE IF EXISTS department;

CREATE TABLE department (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    code TEXT UNIQUE NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE teacher (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    last_name TEXT NOT NULL,
    first_name TEXT NOT NULL,
    middle_name TEXT,
    email TEXT UNIQUE NOT NULL,
    phone TEXT,
    position TEXT,
    department_id INTEGER REFERENCES department(id) ON DELETE SET NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE student_group (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    course INTEGER NOT NULL CHECK (course >= 1 AND course <= 6),
    department_id INTEGER REFERENCES department(id) ON DELETE SET NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE student (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    last_name TEXT NOT NULL,
    first_name TEXT NOT NULL,
    middle_name TEXT,
    email TEXT UNIQUE NOT NULL,
    phone TEXT,
    student_group_id INTEGER REFERENCES student_group(id) ON DELETE SET NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE project_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    color TEXT DEFAULT '#6B7280'
);

CREATE TABLE project (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    status_id INTEGER REFERENCES project_status(id) ON DELETE SET NULL,
    supervisor_id INTEGER REFERENCES teacher(id) ON DELETE SET NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT valid_dates CHECK (end_date >= start_date)
);

CREATE TABLE project_team (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES student(id) ON DELETE CASCADE,
    role TEXT DEFAULT 'Участник',
    joined_at TEXT DEFAULT CURRENT_DATE,
    UNIQUE(project_id, student_id)
);

CREATE TABLE task_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    color TEXT DEFAULT '#6B7280'
);

CREATE TABLE task (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    status_id INTEGER REFERENCES task_status(id) ON DELETE SET NULL,
    priority INTEGER DEFAULT 1 CHECK (priority >= 1 AND priority <= 5),
    deadline TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE task_student (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES task(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES student(id) ON DELETE CASCADE,
    assigned_at TEXT DEFAULT CURRENT_DATE,
    UNIQUE(task_id, student_id)
);

CREATE TABLE file (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    size INTEGER,
    mime_type TEXT,
    project_id INTEGER REFERENCES project(id) ON DELETE CASCADE,
    task_id INTEGER REFERENCES task(id) ON DELETE CASCADE,
    uploaded_by_student_id INTEGER REFERENCES student(id) ON DELETE SET NULL,
    uploaded_by_teacher_id INTEGER REFERENCES teacher(id) ON DELETE SET NULL,
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT file_belongs_to_something CHECK (project_id IS NOT NULL OR task_id IS NOT NULL)
);

CREATE TABLE comment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    project_id INTEGER REFERENCES project(id) ON DELETE CASCADE,
    task_id INTEGER REFERENCES task(id) ON DELETE CASCADE,
    author_student_id INTEGER REFERENCES student(id) ON DELETE SET NULL,
    author_teacher_id INTEGER REFERENCES teacher(id) ON DELETE SET NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT comment_has_target CHECK (project_id IS NOT NULL OR task_id IS NOT NULL),
    CONSTRAINT comment_has_author CHECK (author_student_id IS NOT NULL OR author_teacher_id IS NOT NULL)
);

CREATE TABLE activity_feed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,
    description TEXT NOT NULL,
    project_id INTEGER REFERENCES project(id) ON DELETE CASCADE,
    task_id INTEGER REFERENCES task(id) ON DELETE SET NULL,
    actor_student_id INTEGER REFERENCES student(id) ON DELETE SET NULL,
    actor_teacher_id INTEGER REFERENCES teacher(id) ON DELETE SET NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_project_status ON project(status_id);
CREATE INDEX idx_project_supervisor ON project(supervisor_id);
CREATE INDEX idx_project_dates ON project(start_date, end_date);
CREATE INDEX idx_task_project ON task(project_id);
CREATE INDEX idx_task_status ON task(status_id);
CREATE INDEX idx_student_group ON student(student_group_id);
CREATE INDEX idx_teacher_department ON teacher(department_id);
CREATE INDEX idx_activity_project ON activity_feed(project_id);
CREATE INDEX idx_activity_created ON activity_feed(created_at DESC);

INSERT INTO project_status (name, description, color) VALUES
    ('Планирование', 'Проект на этапе планирования', '#3B82F6'),
    ('В работе', 'Проект активно разрабатывается', '#F59E0B'),
    ('На проверке', 'Проект отправлен на проверку', '#8B5CF6'),
    ('Завершен', 'Проект успешно завершен', '#10B981'),
    ('Отменен', 'Проект отменен', '#EF4444');

INSERT INTO task_status (name, description, color) VALUES
    ('Новая', 'Задача создана, но не начата', '#6B7280'),
    ('В работе', 'Задача в процессе выполнения', '#3B82F6'),
    ('На проверке', 'Задача отправлена на проверку', '#F59E0B'),
    ('Выполнена', 'Задача успешно выполнена', '#10B981'),
    ('Отложена', 'Задача временно отложена', '#EF4444');
