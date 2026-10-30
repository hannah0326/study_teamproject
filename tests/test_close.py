# 작성: 2026-10-26 03:18 KST
"""모집 마감(DB). 어려움 시나리오의 학번 규칙(2026300 + N)을 따른다."""
from dataclasses import replace
from pathlib import Path

import pytest

from teamapp import rules, service
from teamapp.rules import Decision
from teamapp.service import User
from tests.fixtures.runners import DbRunner
from tests.fixtures.scenarios import HARD, play

FIX = Path(__file__).parent / "fixtures"
ADMIN = User(1, "admin", "관리자", True)
BASE = 2026300

pytestmark = pytest.mark.db


def no(n: int) -> str:
    return str(BASE + n)


@pytest.fixture
def run(db, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "시험용-관리자")
    service.ensure_admin()
    service.start_from_roster(ADMIN, (FIX / "어려움.csv").read_bytes(), 4)
    return DbRunner(db)


def admin(run) -> User:
    return run.user("admin")


def test_close_rejects_pending_and_dissolves_single(run):
    before = replace(HARD, steps=HARD.steps[:13])  # 마감 직전: 학생13 대기, 팀4는 학생10 혼자
    assert all(r.ok for r in play(before, run))
    assert service.close_recruitment(admin(run)) == Decision("승인", "모집을 마감함")

    assert run.application_status(no(13)) == "거절"
    assert run.application_reason(no(13)) == "모집 마감"
    left = {s.student_no for s in run.unassigned()}
    assert no(10) in left and no(13) in left and len(left) == 8
    teams = run.teams()
    assert teams[4] == []
    assert [s.student_no for s in teams[1]] == [no(1), no(4), no(7)]
    assert service.snapshot(run.user(no(1))).closed is True


def test_apply_after_close_blocked(run):
    run.apply(no(1), 1)
    service.close_recruitment(admin(run))
    assert run.apply(no(2), 2) == Decision("막힘", rules.REASON_CLOSED)
    assert run.application_status(no(2)) is None


def test_close_requires_admin(run):
    with pytest.raises(PermissionError):
        service.close_recruitment(run.user(no(1)))
    with pytest.raises(PermissionError):
        service.close_recruitment(None)
    assert service.snapshot(run.user(no(1))).closed is False


def test_close_before_roster_blocked(db, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "시험용-관리자")
    service.ensure_admin()
    actor = service.login("admin", "시험용-관리자")
    assert service.close_recruitment(actor) == Decision("막힘", "명단을 먼저 올려야 함")


def test_close_twice_blocked(run):
    assert service.close_recruitment(admin(run)).word == "승인"
    assert service.close_recruitment(admin(run)) == Decision("막힘", "이미 마감함")
