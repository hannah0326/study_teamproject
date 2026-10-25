# 작성: 2026-10-26 00:23 KST
"""학생 화면. 서비스는 가짜로 바꾸고 화면 요소의 key, 숨김, 결과 안내만 본다."""
from dataclasses import replace
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from teamapp import boot, service
from teamapp.rules import Decision, Student
from teamapp.service import MyApp, PendingApp, Snapshot, User

APP = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")
ME = User(5, "2026301", "학생1", False)


def stu(n: int, main: str = "테스터", subs: tuple[str, ...] = ()) -> Student:
    return Student(str(2026300 + n), f"학생{n}", main, subs)


EMPTY = Snapshot(
    closed=False, confirmed=False, teams={1: [], 2: [], 3: []},
    pending=[], my_votes={}, my_team=None, my_app=None,
)


class FakeService:
    """snapshot 은 지금 상태를 돌려주고, apply/vote 는 부른 내용을 남긴 뒤 정해 둔 결과를 돌려준다."""

    def __init__(self, state: Snapshot):
        self.state = state
        self.calls = []
        self.reply = Decision("대기", "")
        self.after = None  # 동작 뒤 바뀔 상태

    def snapshot(self, actor):
        return self.state

    def _act(self, *call):
        self.calls.append(call)
        if self.after is not None:
            self.state = self.after
        return self.reply

    def apply(self, actor, team_no):
        return self._act("apply", actor.student_no, team_no)

    def vote(self, actor, applicant_no, yes):
        return self._act("vote", actor.student_no, applicant_no, yes)


@pytest.fixture(autouse=True)
def no_boot(monkeypatch):
    monkeypatch.setattr(boot, "ensure_ready", lambda: None)


@pytest.fixture
def fake(monkeypatch):
    f = FakeService(EMPTY)
    for name in ("snapshot", "apply", "vote"):
        monkeypatch.setattr(service, name, getattr(f, name))
    return f


def run() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=15)
    at.session_state["user"] = ME
    return at.run()


def walk(node):
    for child in node.children.values():
        yield child
        if hasattr(child, "children"):
            yield from walk(child)


def all_keys(at) -> list[str]:
    return [k for k in (getattr(n, "key", None) for n in walk(at.main)) if k]


def keys(at) -> set[str]:
    return set(all_keys(at))


def text_of(node) -> str:
    return " ".join(str(getattr(c, "value", "")) for c in walk(node))


def container_text(at, key) -> str:
    for n in walk(at.main):
        if getattr(n, "key", None) == key and hasattr(n, "children"):
            return text_of(n)
    raise AssertionError(f"{key} 없음")


def test_team_containers_and_apply_buttons(fake):
    at = run()
    assert not at.exception
    assert {"team_1", "team_2", "team_3", "apply_1", "apply_2", "apply_3", "whoami"} <= keys(at)


@pytest.mark.parametrize(
    "state",
    [
        replace(EMPTY, teams={1: [stu(1)], 2: [], 3: []}, my_team=1),
        replace(EMPTY, my_app=MyApp(2, "대기", "")),
        replace(EMPTY, closed=True),
    ],
    ids=["팀 있음", "대기 지원 있음", "마감"],
)
def test_apply_hidden_when_has_team_pending_or_closed(fake, state):
    fake.state = state
    at = run()
    assert not [k for k in keys(at) if k.startswith("apply_")]
    assert {"team_1", "team_2", "team_3"} <= keys(at)


def test_apply_visible_when_full_or_dup(fake):
    fake.state = replace(EMPTY, teams={1: [stu(2), stu(3), stu(4), stu(5)], 2: [stu(6)], 3: []})
    fake.reply = Decision("막힘", "팀이 꽉 참")
    at = run()
    assert {"apply_1", "apply_2"} <= keys(at)
    at.button(key="apply_1").click().run()
    assert fake.calls == [("apply", "2026301", 1)]
    assert container_text(at, "result").startswith("막힘: 팀이 꽉 참")


def test_apply_click_shows_state_after_action(fake):
    """결과 안내와 팀 목록은 동작이 끝난 뒤의 상태여야 한다(동작 전 상태를 그리지 않음)."""
    fake.reply = Decision("승인", "")
    fake.after = replace(EMPTY, teams={1: [], 2: [stu(1)], 3: []}, my_team=2,
                         my_app=MyApp(2, "승인", ""))
    at = run()
    at.button(key="apply_2").click().run()
    assert container_text(at, "result").startswith("승인")
    assert "내 팀" in container_text(at, "team_2")
    assert not [k for k in keys(at) if k.startswith("apply_")]


def test_vote_buttons_keys(fake):
    fake.state = replace(
        EMPTY,
        teams={1: [stu(1)], 2: [stu(2)], 3: []},
        my_team=1,
        pending=[PendingApp(stu(6), 1, {}), PendingApp(stu(7), 2, {})],
    )
    at = run()
    assert {"vote_yes_2026306", "vote_no_2026306"} <= keys(at)
    assert "vote_yes_2026307" not in keys(at)  # 다른 팀의 지원
    at.button(key="vote_no_2026306").click().run()
    assert fake.calls == [("vote", "2026301", "2026306", False)]
    assert container_text(at, "result").startswith("대기")


def test_voted_shows_my_vote_not_buttons(fake):
    fake.state = replace(
        EMPTY,
        teams={1: [stu(1), stu(4)], 2: [], 3: []},
        my_team=1,
        pending=[PendingApp(stu(6), 1, {"2026301": True})],
        my_votes={"2026306": True},
    )
    at = run()
    assert not [k for k in keys(at) if k.startswith("vote_")]
    assert "내 투표: 찬성" in text_of(at.main)


def test_my_team_marker_and_no_team_text(fake):
    fake.state = replace(EMPTY, teams={1: [stu(2)], 2: [stu(1)], 3: []}, my_team=2)
    at = run()
    assert "내 팀" in container_text(at, "team_2")
    assert "내 팀" not in container_text(at, "team_1")
    assert "학생1" in container_text(at, "team_2")

    fake.state = EMPTY
    at = run()
    assert "아직 팀이 없음" in text_of(at.main)


def test_no_refresh_key_and_result_once(fake):
    at = run()
    assert "refresh" not in keys(at)
    names = all_keys(at)
    assert names.count("result") == 1
    assert all(names.count(f"team_{n}") == 1 for n in (1, 2, 3))


@pytest.mark.parametrize(
    "status, reason, notice",
    [("승인", "", "내 지원이 팀1에 승인됨"), ("거절", "", "내 지원이 팀1에서 거절됨")],
)
def test_notice_when_my_waiting_app_is_decided_later(fake, status, reason, notice):
    """지원해서 대기를 받은 뒤 다른 팀원의 표로 결정되면, result 는 그대로 두고 안내를 따로 보인다."""
    fake.reply = Decision("대기", "")
    fake.after = replace(EMPTY, teams={1: [stu(2)], 2: [], 3: []}, my_app=MyApp(1, "대기", ""))
    at = run()
    at.button(key="apply_1").click().run()
    assert container_text(at, "result").startswith("대기")
    assert "내 지원이" not in text_of(at.main)

    decided_team = 1 if status == "승인" else None
    members = [stu(2), stu(1)] if status == "승인" else [stu(2)]
    fake.state = replace(EMPTY, teams={1: members, 2: [], 3: []}, my_team=decided_team,
                         my_app=MyApp(1, status, reason))
    at.run()
    assert container_text(at, "result").startswith("대기")  # 동작 직후의 결과는 바꾸지 않음
    assert notice in text_of(at.main)


def test_no_notice_when_result_was_already_final_or_from_vote(fake):
    fake.reply = Decision("승인", "")
    fake.after = replace(EMPTY, teams={1: [stu(1)], 2: [], 3: []}, my_team=1, my_app=MyApp(1, "승인", ""))
    at = run()
    at.button(key="apply_1").click().run()
    assert "내 지원이" not in text_of(at.main)

    # 투표의 결과가 대기여도 그것은 내 지원이 아니므로 안내하지 않음
    fake.state = replace(fake.after, pending=[PendingApp(stu(6), 1, {})])
    fake.reply = Decision("대기", "")
    fake.after = None
    at.run()
    at.button(key="vote_yes_2026306").click().run()
    assert container_text(at, "result").startswith("대기")
    assert "내 지원이" not in text_of(at.main)


def test_signed_out_when_account_gone(fake):
    """명단을 다시 올려 계정이 없어지면 로그아웃시키고 다시 로그인하라고 안내한다."""
    fake.state = replace(EMPTY, signed_in=False)
    at = run()
    assert not at.exception
    assert "user" not in at.session_state
    assert {"login_student_no", "login_password", "login_submit"} <= keys(at)
    assert not [k for k in keys(at) if k.startswith(("apply_", "team_"))]
    assert container_text(at, "result") == f"막힘: {service.REASON_RELOGIN}"


def test_log_error_writes_kind_only(capsys):
    from teamapp import ui_common

    ui_common.log_error("처리 중 오류", RuntimeError("postgresql://user:SECRETPW@host:5432/db"))
    out = capsys.readouterr().out
    assert out == "처리 중 오류: RuntimeError\n"


def test_snapshot_error_is_shown_without_secrets(fake, monkeypatch):
    def boom(actor):
        raise RuntimeError("postgresql://user:SECRETPW@host:5432/db")

    monkeypatch.setattr(service, "snapshot", boom)
    at = run()
    assert not at.exception
    page = text_of(at.main)
    assert "SECRETPW" not in page and "postgresql" not in page
    assert "result" in keys(at)
