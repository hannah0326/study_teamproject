# 작성: 2026-10-26 00:05 KST
"""지원과 투표 서비스(DB). 어려움 시나리오의 학번 규칙(2026300 + N)을 따른다."""
from dataclasses import replace
from pathlib import Path

import pytest

from teamapp import rules, service
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


def count(db, sql, *args) -> int:
    with db.connection() as conn:
        return conn.execute(sql, args).fetchone()[0]


def test_apply_empty_team_approved_and_member_row(db, run):
    d = run.apply(no(1), 1)
    assert d.word == "승인"
    assert count(db, "select count(*) from tf_members") == 1
    assert run.application_status(no(1)) == "승인"
    assert [s.student_no for s in run.teams()[1]] == [no(1)]


def test_apply_blocked_not_recorded(db, run):
    run.apply(no(1), 1)
    before = count(db, "select count(*) from tf_applications")
    d = run.apply(no(1), 2)
    assert d.word == "막힘" and d.reason == rules.REASON_HAS_TEAM
    assert count(db, "select count(*) from tf_applications") == before


def test_apply_after_block_can_apply_elsewhere(db, run):
    first = replace(HARD, steps=HARD.steps[:10])  # 어려움 1~10단계: 팀3에 학생11, 학생15
    assert all(r.ok for r in play(first, run))
    blocked = run.apply(no(14), 3)
    assert blocked.word == "막힘" and blocked.reason == rules.REASON_SLOT
    assert run.application_status(no(14)) is None
    assert run.apply(no(14), 4).word == "승인"


def test_apply_closed_and_unknown_team_and_admin(db, run):
    with db.connection() as conn:
        conn.execute("insert into tf_settings values ('closed', '1')")
    assert run.apply(no(1), 1) == rules.Decision("막힘", rules.REASON_CLOSED)
    with db.connection() as conn:
        conn.execute("delete from tf_settings where key = 'closed'")
    assert run.apply(no(1), 9).word == "막힘"
    assert service.apply(ADMIN, 1).word == "막힘"
    assert count(db, "select count(*) from tf_applications") == 0


def test_vote_requires_member_and_pending(db, run):
    run.apply(no(1), 1)
    run.apply(no(4), 1)
    assert run.vote(no(1), no(4), True).word == "승인"
    run.apply(no(7), 1)
    assert run.vote(no(2), no(7), True).word == "막힘"  # 팀원이 아님
    assert run.vote(no(1), no(7), True).word == "대기"
    assert run.vote(no(1), no(7), True).word == "막힘"  # 두 번째 투표
    assert count(db, "select count(*) from tf_votes") == 2  # 학생4에 대한 1표 + 학생7에 대한 1표
    assert run.application_status(no(7)) == "대기"
    # 이미 결정된 지원에 늦게 온 표는 상태를 바꾸지 않는다
    late = run.vote(no(4), no(7), False)
    assert late.word == "거절"
    after = run.vote(no(1), no(7), True)
    assert after.word == "거절" and run.application_status(no(7)) == "거절"
    assert run.vote(no(1), no(9), True).word == "막힘"  # 지원이 없음


def test_vote_order_is_finish_order(db, run):
    first = replace(HARD, steps=HARD.steps[:6])  # 팀2: 학생2, 학생8, 대기 지원 학생5·학생6
    assert all(r.ok for r in play(first, run))
    run.vote(no(2), no(6), True)
    assert run.vote(no(8), no(6), True).word == "승인"  # 학생6의 표가 먼저 끝남
    run.vote(no(2), no(5), True)
    run.vote(no(8), no(5), True)
    last = run.vote(no(6), no(5), True)
    assert last.word == "거절" and last.reason.startswith("승인 직전 검사에서")
    assert run.application_status(no(5)) == "거절"
    assert [s.student_no for s in run.teams()[2]] == [no(2), no(8), no(6)]


def test_slot_unique_conflict_rejects_with_reason(db, run, monkeypatch):
    run.apply(no(1), 1)
    run.apply(no(4), 1)
    monkeypatch.setattr(service, "free_slot", lambda conn, team_id: 1)  # 이미 찬 자리를 고름
    d = run.vote(no(1), no(4), True)
    assert d.word == "거절" and d.reason == "먼저 도착한 학생이 자리를 차지함"
    assert run.application_status(no(4)) == "거절"
    assert run.application_reason(no(4)) == "먼저 도착한 학생이 자리를 차지함"
    assert [s.student_no for s in run.teams()[1]] == [no(1)]
    assert count(db, "select count(*) from tf_votes") == 1  # 투표 기록은 남음


def test_rejected_can_reapply_same_team(db, run):
    run.apply(no(1), 1)
    run.apply(no(4), 1)
    assert run.vote(no(1), no(4), False).word == "거절"
    assert run.apply(no(4), 1).word == "대기"


def test_free_slot_is_smallest_empty(db, run):
    run.apply(no(1), 1)
    run.apply(no(4), 1)
    run.vote(no(1), no(4), True)
    with db.connection() as conn:
        (team_id,) = conn.execute("select id from tf_teams where name = '팀1'").fetchone()
        assert service.free_slot(conn, team_id) == 3
        conn.execute("delete from tf_members where slot_no = 1")
        assert service.free_slot(conn, team_id) == 1
