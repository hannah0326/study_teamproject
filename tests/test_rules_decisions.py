# 작성: 2026-10-25 23:30 KST
from teamapp import rules
from teamapp.rules import Decision
from tests.helpers import FD, PL, PT, RW, TT, WP, mk

OPEN = dict(closed=False, has_team=False, has_pending=False)


def test_apply_check_order():
    team = [mk("1", PL), mk("2", WP), mk("3", FD), mk("4", TT)]  # 꽉 참
    dup = mk("9", PL)  # 주 역할도 겹침
    flags = dict(closed=True, has_team=True, has_pending=True)
    assert rules.check_apply(team, dup, **flags) == rules.REASON_CLOSED
    flags["closed"] = False
    assert rules.check_apply(team, dup, **flags) == rules.REASON_HAS_TEAM
    flags["has_team"] = False
    assert rules.check_apply(team, dup, **flags) == rules.REASON_PENDING
    flags["has_pending"] = False
    assert rules.check_apply(team, dup, **flags) == rules.REASON_FULL
    assert rules.check_apply(team[:3], dup, **flags) == rules.REASON_DUP


def test_apply_blocked_when_tester_presenter_team_gets_writer():
    team = [mk("1", TT), mk("2", PT)]
    assert rules.check_apply(team, mk("3", RW), **OPEN) == rules.REASON_SLOT


def test_apply_allowed_when_spare_equals_unmet():
    assert rules.check_apply([], mk("1", PL), **OPEN) is None
    # 팀원 2명(미충족 1) + 지원자가 채워 주지 못해도 남는 자리 1 ≥ 미충족 1 이면 통과
    assert rules.check_apply([mk("1", PL), mk("2", FD)], mk("3", TT), **OPEN) is None


def test_decide_apply_empty_team_is_approved():
    assert rules.decide_apply([], mk("1", PL), **OPEN) == Decision("승인", "")


def test_decide_apply_nonempty_is_pending():
    d = rules.decide_apply([mk("1", PL)], mk("2", WP), **OPEN)
    assert d.word == "대기"


def test_decide_apply_blocked_word_and_reason():
    d = rules.decide_apply([mk("1", PL)], mk("2", PL), **OPEN)
    assert d == Decision("막힘", rules.REASON_DUP)


def test_recheck_uses_given_members():
    applicant = mk("6", WP, RW)
    assert rules.recheck([mk("5", WP, FD)], applicant) == rules.REASON_DUP
    assert rules.recheck([mk("2", PL)], applicant) is None


def test_recheck_full_and_slot():
    full = [mk("1", PL), mk("2", WP), mk("3", FD), mk("4", TT)]
    assert rules.recheck(full, mk("5", RW)) == rules.REASON_FULL
    assert rules.recheck([mk("1", TT), mk("2", PT)], mk("3", RW)) == rules.REASON_SLOT


def test_vote_no_rejects_immediately():
    a, b, app = mk("1", PL), mk("2", FD), mk("3", WP)
    d = rules.decide_vote([a, b], {}, app, a, False, status="대기")
    assert d.word == "거절"


def test_vote_yes_waits_for_others():
    a, b, app = mk("1", PL), mk("2", FD), mk("3", WP)
    assert rules.decide_vote([a, b], {}, app, a, True, status="대기").word == "대기"


def test_vote_all_yes_approves():
    a, b, app = mk("1", PL), mk("2", FD), mk("3", WP)
    d = rules.decide_vote([a, b], {"2": True}, app, a, True, status="대기")
    assert d.word == "승인"


def test_vote_all_yes_but_recheck_fails_rejects_with_prefix():
    a, b, app = mk("2", PL), mk("5", WP, FD), mk("6", WP, RW)
    d = rules.decide_vote([a, b], {"2": True}, app, b, True, status="대기")
    assert d.word == "거절"
    assert d.reason.startswith("승인 직전 검사에서")
    assert rules.REASON_DUP in d.reason


def test_vote_on_decided_application_keeps_status():
    a, app = mk("1", PL), mk("3", WP)
    for yes in (True, False):
        for status in ("거절", "승인"):
            d = rules.decide_vote([a], {}, app, a, yes, status=status)
            assert d.word == status
