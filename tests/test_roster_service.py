# 작성: 2026-10-25 23:24 KST
from pathlib import Path

import pytest

from teamapp import service
from teamapp.service import User

FIX = Path(__file__).parent / "fixtures"
ADMIN = User(1, "admin", "관리자", True)


def csv_bytes(name: str) -> bytes:
    return (FIX / f"{name}.csv").read_bytes()


def count(db, sql, *args) -> int:
    with db.connection() as conn:
        return conn.execute(sql, args).fetchone()[0]


@pytest.fixture
def admin_ready(db, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "시험용-관리자")
    service.ensure_admin()


@pytest.mark.parametrize("actor", [None, User(5, "2026101", "학생1", False)])
def test_start_requires_admin(actor):
    with pytest.raises(PermissionError):
        service.start_from_roster(actor, b"", 3)


@pytest.mark.db
def test_start_creates_students_teams_roles(db, admin_ready):
    d = service.start_from_roster(ADMIN, csv_bytes("쉬움"), 3)
    assert d.word == "승인"
    assert count(db, "select count(*) from tf_students where not is_admin") == 8
    assert count(db, "select count(*) from tf_students where is_admin") == 1
    with db.connection() as conn:
        names = [r[0] for r in conn.execute("select name from tf_teams order by id")]
    assert names == ["팀1", "팀2", "팀3"]
    # 2026108(테스터; 보고서 작성자, 발표자)의 보조 역할 2개, 2026105는 0개
    sub = "select count(*) from tf_student_sub_roles r join tf_students s on s.id = r.student_id " \
          "where s.student_no = %s"
    assert count(db, sub, "2026108") == 2
    assert count(db, sub, "2026105") == 0
    assert service.login("2026101", "1234") is not None


@pytest.mark.db
def test_start_resets_state_keeps_admin(db, admin_ready):
    service.start_from_roster(ADMIN, csv_bytes("쉬움"), 3)
    with db.connection() as conn:
        s1, s2 = [r[0] for r in conn.execute("select id from tf_students where not is_admin limit 2")]
        t = conn.execute("select id from tf_teams limit 1").fetchone()[0]
        conn.execute("insert into tf_members values (%s, 1, %s)", (t, s1))
        a = conn.execute(
            "insert into tf_applications (team_id, student_id, status) values (%s, %s, '대기') "
            "returning id", (t, s2)).fetchone()[0]
        conn.execute("insert into tf_votes values (%s, %s, '찬성')", (a, s1))
        conn.execute("insert into tf_settings values ('closed', '1')")
    d = service.start_from_roster(ADMIN, csv_bytes("어려움"), 4)
    assert d.word == "승인"
    assert count(db, "select count(*) from tf_students where not is_admin") == 16
    assert count(db, "select count(*) from tf_students where is_admin") == 1
    assert count(db, "select count(*) from tf_teams") == 4
    for table in ("tf_members", "tf_applications", "tf_votes"):
        assert count(db, f"select count(*) from {table}") == 0
    assert count(db, "select count(*) from tf_settings where key = 'closed'") == 0
    assert service.login("admin", "시험용-관리자") is not None


@pytest.mark.db
def test_start_invalid_csv_keeps_old_state(db, admin_ready):
    service.start_from_roster(ADMIN, csv_bytes("쉬움"), 3)
    bad = b"student_no,name,main_role\n1,a,b\n"
    d = service.start_from_roster(ADMIN, bad, 5)
    assert d.word == "막힘" and d.reason
    assert count(db, "select count(*) from tf_students where not is_admin") == 8
    assert count(db, "select count(*) from tf_teams") == 3


@pytest.mark.db
def test_start_team_count_greater_than_students(db, admin_ready):
    d = service.start_from_roster(ADMIN, csv_bytes("쉬움"), 10)
    assert d.word == "승인"
    assert count(db, "select count(*) from tf_teams") == 10


@pytest.mark.db
@pytest.mark.parametrize("bad_count", [0, 11, -1])
def test_start_team_count_out_of_range(db, admin_ready, bad_count):
    service.start_from_roster(ADMIN, csv_bytes("쉬움"), 3)
    d = service.start_from_roster(ADMIN, csv_bytes("어려움"), bad_count)
    assert d.word == "막힘"
    assert count(db, "select count(*) from tf_students where not is_admin") == 8


@pytest.mark.db
def test_passwords_are_hashed_per_student(db, admin_ready):
    service.start_from_roster(ADMIN, csv_bytes("쉬움"), 3)
    with db.connection() as conn:
        hashes = [r[0] for r in conn.execute("select password_hash from tf_students where not is_admin")]
    assert all(h.startswith("$2b$") and h != "1234" for h in hashes)
    assert len(set(hashes)) == len(hashes)  # 학생마다 소금 값이 다름
