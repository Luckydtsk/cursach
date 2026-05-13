-- Консультации преподавателя со студентами (дата, длительность в минутах)

CREATE TABLE IF NOT EXISTS consultation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL REFERENCES teacher(id) ON DELETE CASCADE,
    student_id INTEGER NOT NULL REFERENCES student(id) ON DELETE CASCADE,
    consultation_date TEXT NOT NULL,
    duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
    note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_consultation_teacher ON consultation(teacher_id);
CREATE INDEX IF NOT EXISTS idx_consultation_student ON consultation(student_id);
CREATE INDEX IF NOT EXISTS idx_consultation_teacher_student ON consultation(teacher_id, student_id);
CREATE INDEX IF NOT EXISTS idx_consultation_date ON consultation(consultation_date DESC);
