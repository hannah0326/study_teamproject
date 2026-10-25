# 작성: 2026-10-25 23:26 KST
from pathlib import Path

import pytest
from streamlit.proto.TextInput_pb2 import TextInput
from streamlit.testing.v1 import AppTest

from teamapp import boot, service
from teamapp.service import User

APP = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")
STUDENT = User(5, "2026301", "학생1(PL;RW)", False)
ADMIN = User(1, "admin", "관리자", True)


@pytest.fixture(autouse=True)
def no_boot(monkeypatch):
    monkeypatch.setattr(boot, "ensure_ready", lambda: None)


def run(user=None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=15)
    if user is not None:
        at.session_state["user"] = user
    return at.run()


def walk(node):
    for child in node.children.values():
        yield child
        if hasattr(child, "children"):
            yield from walk(child)


def keys(at) -> set[str]:
    return {getattr(n, "key", None) for n in walk(at.main)} - {None}


def container_text(at, key) -> str | None:
    for n in walk(at.main):
        if getattr(n, "key", None) == key and hasattr(n, "children"):
            return " ".join(str(getattr(c, "value", "")) for c in walk(n))
    return None


def test_login_screen_keys_and_no_whoami():
    at = run()
    assert not at.exception
    assert {"login_student_no", "login_password", "login_submit", "result"} <= keys(at)
    assert "whoami" not in keys(at)
    assert at.text_input(key="login_password").proto.type == TextInput.PASSWORD


def test_login_success_shows_name_in_whoami(monkeypatch):
    monkeypatch.setattr(service, "login", lambda no, pw: STUDENT if (no, pw) == ("2026301", "1234") else None)
    at = run()
    at.text_input(key="login_student_no").input("2026301")
    at.text_input(key="login_password").input("1234")
    at.button(key="login_submit").click().run()
    assert "학생1(PL;RW)" in container_text(at, "whoami")
    assert "login_submit" not in keys(at)


def test_login_failure_says_blocked_without_hint(monkeypatch):
    monkeypatch.setattr(service, "login", lambda no, pw: None)
    at = run()
    at.text_input(key="login_student_no").input("2026301")
    at.text_input(key="login_password").input("틀림")
    at.button(key="login_submit").click().run()
    text = container_text(at, "result")
    assert text.startswith("막힘")
    assert "whoami" not in keys(at)


def test_unexpected_error_is_shown_without_secrets(monkeypatch):
    def boom(no, pw):
        raise RuntimeError("postgresql://user:SECRETPW@host:5432/db")

    monkeypatch.setattr(service, "login", boom)
    at = run()
    at.text_input(key="login_student_no").input("2026301")
    at.text_input(key="login_password").input("1234")
    at.button(key="login_submit").click().run()
    assert not at.exception
    text = container_text(at, "result")
    assert text.startswith("막힘")
    assert "SECRETPW" not in text and "postgresql" not in text


def test_admin_screen_keys():
    at = run(ADMIN)
    assert {"whoami", "result", "admin_roster_file", "admin_team_count", "admin_start"} <= keys(at)
    assert "관리자" in container_text(at, "whoami")


def test_student_screen_has_no_admin_keys():
    at = run(STUDENT)
    assert "whoami" in keys(at)
    assert not [k for k in keys(at) if k.startswith("admin_")]


def test_admin_start_without_file_is_blocked():
    at = run(ADMIN)
    at.button(key="admin_start").click().run()
    assert container_text(at, "result").startswith("막힘")
