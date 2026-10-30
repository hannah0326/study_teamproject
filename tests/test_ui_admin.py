# 작성: 2026-10-26 03:32 KST
"""관리자 화면. 서비스는 가짜로 바꾸고 key, 안내, 결과만 본다."""
from dataclasses import replace
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from teamapp import boot, service
from teamapp.rules import Decision, Student
from teamapp.service import AdminView, Proposal, Snapshot, User

APP = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")
ADMIN = User(1, "admin", "관리자", True)
STUDENT = User(5, "2026301", "학생1", False)


def stu(n: int, main: str = "테스터", subs: tuple[str, ...] = ()) -> Student:
    return Student(str(2026300 + n), f"학생{n}", main, subs)


VIEW = AdminView(
    roster_loaded=True, closed=False, confirmed=False,
    teams={1: [stu(1, "기획자")], 2: [], 3: []}, free=[stu(7), stu(8)],
    proposal=None, status=None,
)


class FakeAdmin:
    def __init__(self):
        self.view = VIEW
        self.calls = []
        self.reply = Decision("승인", "모집을 마감함")
        self.statuses = ["1차 모델(m/first:free) 응답을 기다리는 중 … 경과 0초"]
        self.after = None

    def admin_view(self, actor):
        return self.view

    def _act(self, name):
        self.calls.append(name)
        if self.after is not None:
            self.view = self.after
        return self.reply

    def close_recruitment(self, actor):
        return self._act("close")

    def propose_assignment(self, actor, on_status=lambda s: None, *, call=None):
        for s in self.statuses:
            on_status(s)
        return self._act("propose")

    def confirm_assignment(self, actor):
        return self._act("confirm")


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    monkeypatch.setattr(boot, "ensure_ready", lambda: None)
    f = FakeAdmin()
    for name in ("admin_view", "close_recruitment", "propose_assignment", "confirm_assignment"):
        monkeypatch.setattr(service, name, getattr(f, name))
    empty = Snapshot(False, False, {1: [], 2: [], 3: []}, [], {}, None, None)
    monkeypatch.setattr(service, "snapshot", lambda actor: empty)
    return f


def run(user=ADMIN) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=15)
    at.session_state["user"] = user
    return at.run()


def walk(node):
    for child in node.children.values():
        yield child
        if hasattr(child, "children"):
            yield from walk(child)


def all_keys(at) -> list[str]:
    return [k for k in (getattr(n, "key", None) for n in walk(at.main)) if k]


def text_of(node) -> str:
    return " ".join(str(getattr(c, "value", "")) for c in walk(node))


def container_text(at, key) -> str:
    for n in walk(at.main):
        if getattr(n, "key", None) == key and hasattr(n, "children"):
            return text_of(n)
    raise AssertionError(f"{key} 없음")


ADMIN_ONLY = ("admin_close", "admin_assign", "admin_confirm", "assign_status", "unassigned")


def test_admin_keys_once_each(fake):
    at = run()
    assert not at.exception
    names = all_keys(at)
    for key in (*ADMIN_ONLY, "team_1", "team_2", "team_3", "result", "whoami"):
        assert names.count(key) == 1, key
    assert "refresh" not in names


def test_student_screen_has_no_admin_parts(fake):
    names = all_keys(run(STUDENT))
    assert not [k for k in names if k in ADMIN_ONLY or k.startswith("admin_")]


def test_unassigned_shows_names(fake):
    at = run()
    text = container_text(at, "unassigned")
    assert "학생7" in text and "학생8" in text
    fake.view = replace(VIEW, free=[])
    assert "팀이 없는 학생이 없음" in container_text(run(), "unassigned")


def test_team_containers_show_members(fake):
    at = run()
    assert "학생1" in container_text(at, "team_1")


def test_close_click(fake):
    fake.after = replace(VIEW, closed=True, teams={1: [], 2: [], 3: []}, free=[stu(1, "기획자"), stu(7), stu(8)])
    at = run()
    at.button(key="admin_close").click().run()
    assert fake.calls == ["close"]
    assert container_text(at, "result").startswith("승인: 모집을 마감함")
    assert "학생1" in container_text(at, "unassigned")  # 동작 뒤의 상태를 그림


def test_assign_click_shows_status_and_proposal(fake):
    proposal = Proposal("ai1", "1차 모델(m/first:free)의 배정안이 5가지 검사를 통과함",
                        {1: [stu(7)], 2: [stu(8)], 3: []})
    fake.view = replace(VIEW, closed=True)
    fake.after = replace(VIEW, closed=True, proposal=proposal, status=proposal.message)
    fake.reply = Decision("승인", "배정안을 만듦")
    at = run()
    at.button(key="admin_assign").click().run()
    assert fake.calls == ["propose"]
    assert container_text(at, "result").startswith("승인")
    status = container_text(at, "assign_status")
    assert "1차 모델(m/first:free)의 배정안이 5가지 검사를 통과함" in status
    assert "학생7" in status and "학생8" in status


def test_no_assignment_reason_in_assign_status(fake):
    message = "규칙을 지키는 배정이 없음: 팀3에 웹 프로그래머를 맡을 학생이 없음"
    fake.view = replace(VIEW, closed=True)
    fake.after = replace(VIEW, closed=True, status=message)
    fake.reply = Decision("막힘", "규칙을 지키는 배정이 없음")
    fake.statuses = [message]
    at = run()
    at.button(key="admin_assign").click().run()
    assert container_text(at, "result") == "막힘: 규칙을 지키는 배정이 없음"
    assert "팀3에 웹 프로그래머를 맡을 학생이 없음" in container_text(at, "assign_status")


def test_attempt_lines_shown_as_plain_text(fake):
    """모델별 줄은 마크다운으로 해석하지 않는다: ':free:' 같은 글이 이모지로 바뀌지 않고 그대로 보여야 함."""
    line = "1차 모델(m/first:free) — 사용량이 많다며 거절함(429) (2.2초) — x:free: is *limited*"
    fake.view = replace(VIEW, closed=True, status="3차 모델까지 실패하여 앱이 직접 배정함\n" + line)
    at = run()
    assert line in [t.value for t in at.text]
    assert all(line not in str(getattr(m, "value", "")) for m in at.markdown)


def test_confirm_click(fake):
    fake.reply = Decision("승인", "배정안을 확정함")
    at = run()
    at.button(key="admin_confirm").click().run()
    assert fake.calls == ["confirm"]
    assert container_text(at, "result").startswith("승인: 배정안을 확정함")


def test_admin_errors_hidden(fake, monkeypatch):
    def boom(actor):
        raise RuntimeError("postgresql://user:SECRETPW@host:5432/db")

    monkeypatch.setattr(service, "close_recruitment", boom)
    monkeypatch.setattr(service, "admin_view", boom)
    at = run()
    assert not at.exception
    at.button(key="admin_close").click().run()
    page = text_of(at.main)
    assert "SECRETPW" not in page and "postgresql" not in page
    assert container_text(at, "result").startswith("막힘")
