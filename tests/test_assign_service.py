# 작성: 2026-10-26 03:24 KST
"""배정안 만들기·보관·확정(DB). AI는 가짜 call 로만 부른다."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from teamapp import rules, service, solver
from teamapp.ai import AiResult
from teamapp.rules import Decision
from teamapp.service import User
from tests.fixtures.runners import DbRunner
from tests.fixtures.scenarios import HARD, play

FIX = Path(__file__).parent / "fixtures"
ADMIN = User(1, "admin", "관리자", True)
FAKE_KEY = "sk-or-v1-FAKEKEY0123456789"

pytestmark = pytest.mark.db


@pytest.fixture
def run(db, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "시험용-관리자")
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    service.ensure_admin()
    service.start_from_roster(ADMIN, (FIX / "어려움.csv").read_bytes(), 4)
    return DbRunner(db)


@pytest.fixture
def closed(run):
    """어려움 시나리오를 마감(14단계)까지 진행한 상태."""
    assert all(r.ok for r in play(replace(HARD, steps=HARD.steps[:14]), run))
    return run


def admin(run) -> User:
    return run.user("admin")


def good_call(run):
    """지금 DB 상태에 맞는 올바른 배정안을 돌려주는 가짜 AI."""
    calls = []

    def call(model, messages):
        calls.append(model)
        view = service.admin_view(admin(run))
        found = solver.solve(view.teams, view.free).assignment
        text = json.dumps({"teams": {str(n): [s.student_no for s in m] for n, m in found.items()}})
        return AiResult(True, text, None, 2.5)

    call.calls = calls
    return call


def failing_call(model, messages):
    return AiResult(False, None, "http_429", 0.4, "Rate limit exceeded: free-models-per-day")


def count(db, sql, *args) -> int:
    with db.connection() as conn:
        return conn.execute(sql, args).fetchone()[0]


def test_propose_stores_and_confirm_persists(db, closed):
    statuses = []
    d = service.propose_assignment(admin(closed), statuses.append, call=good_call(closed))
    assert d.word == "승인"
    view = service.admin_view(admin(closed))
    assert view.proposal is not None and view.proposal.source == "ai1"
    assert sorted(s.student_no for m in view.proposal.teams.values() for s in m) == sorted(
        s.student_no for s in view.free
    )
    assert any("1차 모델" in s for s in statuses)
    assert count(db, "select count(*) from tf_ai_logs where step = 1 and result = 'ok'") == 1

    assert service.confirm_assignment(admin(closed)) == Decision("승인", "배정안을 확정함")
    assert closed.unassigned() == []
    teams = closed.teams()
    assert rules.validate_assignment(teams, [], {}) == []
    # 새 브라우저(새 조회)에서도 확정한 팀 구성이 그대로 보임
    again = service.admin_view(admin(closed))
    assert again.confirmed and again.free == [] and again.teams == teams
    assert service.snapshot(closed.user("2026301")).confirmed is True


def test_failures_fall_back_to_solver_and_log(db, closed):
    d = service.propose_assignment(admin(closed), lambda s: None, call=failing_call)
    assert d.word == "승인"
    view = service.admin_view(admin(closed))
    assert view.proposal.source == "solver" and "앱이 직접 배정함" in view.status
    # 관리자 화면의 배정 안내에 모델별 결과와 실패 이유가 남음(5항 화면 근거)
    lines = view.status.splitlines()
    assert lines[0] == "3차 모델까지 실패하여 앱이 직접 배정함"
    assert [ln[:2] for ln in lines[1:]] == ["1차", "2차", "3차"]
    assert all("429" in ln and "free-models-per-day" in ln and "0.4초" in ln for ln in lines[1:])
    assert count(db, "select count(*) from tf_ai_logs where result = 'http_429'") == 3
    assert count(db, "select count(*) from tf_ai_logs where detail like %s "
                     "and started_at is not null and started_at <= created_at", "%free-models-per-day%") == 3


def test_confirm_twice_blocked(closed):
    service.propose_assignment(admin(closed), lambda s: None, call=failing_call)
    assert service.confirm_assignment(admin(closed)).word == "승인"
    assert service.confirm_assignment(admin(closed)) == Decision("막힘", "이미 확정함")
    assert service.propose_assignment(admin(closed), lambda s: None, call=failing_call) == Decision(
        "막힘", "이미 확정함"
    )


def test_confirm_without_proposal_blocked(closed):
    assert service.confirm_assignment(admin(closed)) == Decision("막힘", "확정할 배정안이 없음")


def test_propose_before_close_blocked(run):
    def never(model, messages):
        raise AssertionError("AI를 부르면 안 됨")

    assert service.propose_assignment(admin(run), lambda s: None, call=never) == Decision(
        "막힘", "모집을 먼저 마감해야 함"
    )


def test_propose_and_confirm_require_admin(closed):
    student = closed.user("2026301")
    with pytest.raises(PermissionError):
        service.propose_assignment(student, lambda s: None, call=failing_call)
    with pytest.raises(PermissionError):
        service.confirm_assignment(student)
    with pytest.raises(PermissionError):
        service.admin_view(student)


def test_infeasible_never_calls_ai(db, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "시험용-관리자")
    service.ensure_admin()
    roster = (
        "student_no,name,main_role,sub_roles\n"
        "9001,가,기획자,\n9002,나,테스터,\n9003,다,발표자,\n9004,라,보고서 작성자,\n"
    ).encode()
    service.start_from_roster(ADMIN, roster, 2)
    service.close_recruitment(ADMIN)

    def never(model, messages):
        raise AssertionError("AI를 부르면 안 됨")

    d = service.propose_assignment(ADMIN, lambda s: None, call=never)
    assert d == Decision("막힘", "규칙을 지키는 배정이 없음")
    view = service.admin_view(ADMIN)
    assert view.proposal is None
    assert "웹 프로그래머를 맡을 학생이 없음" in view.status
    assert service.confirm_assignment(ADMIN) == Decision("막힘", "확정할 배정안이 없음")


def test_confirm_revalidates_against_current_state(db, closed):
    service.propose_assignment(admin(closed), lambda s: None, call=failing_call)
    view = service.admin_view(admin(closed))
    moved = view.free[0]
    with db.connection() as conn:  # 배정안을 만든 뒤 상태가 바뀜(그 학생이 이미 팀에 들어감)
        (sid,) = conn.execute("select id from tf_students where student_no = %s", (moved.student_no,)).fetchone()
        (tid,) = conn.execute("select id from tf_teams where name = '팀4'").fetchone()
        conn.execute("insert into tf_members values (%s, 1, %s)", (tid, sid))
    d = service.confirm_assignment(admin(closed))
    assert d.word == "막힘" and d.reason.startswith("배정안이 지금 상태와 맞지 않음")
    assert service.admin_view(admin(closed)).confirmed is False


def test_ai_logs_have_no_key(db, closed):
    service.propose_assignment(admin(closed), lambda s: None, call=failing_call)
    with db.connection() as conn:
        rows = conn.execute("select * from tf_ai_logs").fetchall()
    assert rows and all(FAKE_KEY not in str(r) for r in rows)


def test_reupload_clears_proposal_and_confirm(closed):
    service.propose_assignment(admin(closed), lambda s: None, call=failing_call)
    service.confirm_assignment(admin(closed))
    service.start_from_roster(ADMIN, (FIX / "어려움.csv").read_bytes(), 4)
    view = service.admin_view(admin(closed))
    assert not view.closed and not view.confirmed and view.proposal is None and view.status is None
