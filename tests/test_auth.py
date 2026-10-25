# 작성: 2026-10-25 23:26 KST
import pytest

from teamapp import service
from teamapp.service import User


def _add_student(db, no="2026301", name="학생1", password="1234"):
    with db.connection() as conn:
        conn.execute(
            "insert into tf_students (student_no, name, main_role, password_hash) "
            "values (%s, %s, '기획자', %s)",
            (no, name, service.hash_password(password)),
        )


def test_hash_password_is_bcrypt_and_verifies():
    h = service.hash_password("1234")
    assert h.startswith("$2b$") and h != "1234"
    assert service.verify_password("1234", h)
    assert not service.verify_password("0000", h)


def test_require_admin_rejects_none_and_student():
    student = User(1, "2026301", "학생1", False)
    for actor in (None, student):
        with pytest.raises(PermissionError):
            service.require_admin(actor)
    service.require_admin(User(2, "admin", "관리자", True))  # 오류 없음


@pytest.mark.db
def test_login_ok_and_wrong_password(db):
    _add_student(db)
    user = service.login("2026301", "1234")
    assert user is not None and user.name == "학생1" and not user.is_admin
    assert service.login("2026301", "0000") is None


@pytest.mark.db
def test_login_trims_student_no(db):
    _add_student(db)
    assert service.login(" 2026301 ", "1234") is not None


@pytest.mark.db
def test_login_unknown_student_none(db):
    assert service.login("9999999", "1234") is None


@pytest.mark.db
def test_password_hash_is_bcrypt_not_plain(db):
    _add_student(db)
    with db.connection() as conn:
        (h,) = conn.execute("select password_hash from tf_students").fetchone()
    assert h.startswith("$2b$") and h != "1234"


@pytest.mark.db
def test_ensure_admin_creates_and_updates(db, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "시험용-가")
    service.ensure_admin()
    admin = service.login("admin", "시험용-가")
    assert admin is not None and admin.is_admin
    monkeypatch.setenv("ADMIN_PASSWORD", "시험용-나")
    service.ensure_admin()
    assert service.login("admin", "시험용-가") is None
    assert service.login("admin", "시험용-나") is not None
    with db.connection() as conn:
        (n,) = conn.execute("select count(*) from tf_students where is_admin").fetchone()
    assert n == 1


@pytest.mark.db
def test_ensure_admin_without_password_fails_with_plain_message(db, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr("teamapp.config.get_secret", lambda name: None)
    with pytest.raises(RuntimeError) as e:
        service.ensure_admin()
    assert "설정되지 않음" in str(e.value)
