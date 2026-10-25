# 작성: 2026-10-25 23:22 KST
import re
from pathlib import Path

import psycopg
import pytest

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"

EXPECTED = {
    "tf_students": {"id", "student_no", "name", "main_role", "password_hash", "is_admin"},
    "tf_student_sub_roles": {"student_id", "role"},
    "tf_teams": {"id", "name"},
    "tf_members": {"team_id", "slot_no", "student_id"},
    "tf_applications": {
        "id", "team_id", "student_id", "status", "reason", "created_at", "decided_at"},
    "tf_votes": {"application_id", "voter_id", "vote"},
    "tf_settings": {"key", "value"},
    "tf_ai_logs": {"id", "created_at", "step", "model", "result", "seconds"},
}


def test_schema_file_defines_only_tf_tables_from_prd():
    names = re.findall(r"create table if not exists (\w+)", SCHEMA.read_text(encoding="utf-8"))
    assert set(names) == set(EXPECTED)
    assert all(n.startswith("tf_") for n in names)


def _student(conn, no, role="기획자", admin=False):
    return conn.execute(
        "insert into tf_students (student_no, name, main_role, password_hash, is_admin) "
        "values (%s, %s, %s, 'x', %s) returning id",
        (no, f"이름{no}", role, admin),
    ).fetchone()[0]


def _team(conn, name="팀1"):
    return conn.execute("insert into tf_teams (name) values (%s) returning id", (name,)).fetchone()[0]


@pytest.mark.db
def test_schema_tables_match_prd_section7(db):
    with db.connection() as conn:
        rows = conn.execute(
            "select table_name, column_name from information_schema.columns "
            "where table_schema = 'public' and table_name like 'tf\\_%'"
        ).fetchall()
    got: dict[str, set] = {}
    for t, c in rows:
        got.setdefault(t, set()).add(c)
    assert got == EXPECTED


@pytest.mark.db
def test_unique_members_slot_and_student(db):
    with db.connection() as conn:
        t1, t2 = _team(conn, "팀1"), _team(conn, "팀2")
        s1, s2 = _student(conn, "1"), _student(conn, "2", "테스터")
        conn.execute("insert into tf_members values (%s, 1, %s)", (t1, s1))
    with pytest.raises(psycopg.errors.UniqueViolation):  # 같은 (팀, 자리)
        with db.connection() as conn:
            conn.execute("insert into tf_members values (%s, 1, %s)", (t1, s2))
    with pytest.raises(psycopg.errors.UniqueViolation):  # 같은 학생이 두 팀
        with db.connection() as conn:
            conn.execute("insert into tf_members values (%s, 1, %s)", (t2, s1))


@pytest.mark.db
@pytest.mark.parametrize("slot", [0, 5])
def test_slot_check_1_to_4(db, slot):
    with db.connection() as conn:
        t, s = _team(conn), _student(conn, "1")
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.connection() as conn:
            conn.execute("insert into tf_members values (%s, %s, %s)", (t, slot, s))


@pytest.mark.db
def test_role_check(db):
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.connection() as conn:
            _student(conn, "1", "마법사")
    with db.connection() as conn:
        s = _student(conn, "2")
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.connection() as conn:
            conn.execute("insert into tf_student_sub_roles values (%s, '마법사')", (s,))


@pytest.mark.db
def test_sub_role_unique_per_student(db):
    with db.connection() as conn:
        s = _student(conn, "1")
        conn.execute("insert into tf_student_sub_roles values (%s, '테스터')", (s,))
    with pytest.raises(psycopg.errors.UniqueViolation):
        with db.connection() as conn:
            conn.execute("insert into tf_student_sub_roles values (%s, '테스터')", (s,))


@pytest.mark.db
def test_one_pending_application_per_student(db):
    with db.connection() as conn:
        t, s = _team(conn), _student(conn, "1")
        conn.execute(
            "insert into tf_applications (team_id, student_id, status) values (%s, %s, '거절')",
            (t, s))
        conn.execute(
            "insert into tf_applications (team_id, student_id, status) values (%s, %s, '대기')",
            (t, s))
    with pytest.raises(psycopg.errors.UniqueViolation):
        with db.connection() as conn:
            conn.execute(
                "insert into tf_applications (team_id, student_id, status) values (%s, %s, '대기')",
                (t, s))


@pytest.mark.db
def test_status_and_vote_checks(db):
    with db.connection() as conn:
        t, s = _team(conn), _student(conn, "1")
    with pytest.raises(psycopg.errors.CheckViolation):
        with db.connection() as conn:
            conn.execute(
                "insert into tf_applications (team_id, student_id, status) values (%s, %s, '보류')",
                (t, s))


@pytest.mark.db
def test_pool_created_once(db):
    assert db.get_pool() is db.get_pool()
