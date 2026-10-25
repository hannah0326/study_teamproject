# 작성: 2026-10-26 00:10 KST
from pathlib import Path

import pytest

from teamapp.engine import Engine
from teamapp.roster import parse_roster
from tests.fixtures.runners import EngineRunner
from tests.fixtures.scenarios import SCENARIOS, play

FIX = Path(__file__).parent / "fixtures"


def make_runner(name: str) -> EngineRunner:
    sc = SCENARIOS[name]
    students = parse_roster((FIX / f"{sc.csv_name}.csv").read_bytes())
    return EngineRunner(Engine(students, sc.team_count))


def test_scenario_counts():
    assert {n: len(s.steps) for n, s in SCENARIOS.items()} == {"쉬움": 6, "중간": 11, "어려움": 15}


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_scenario_matches_expected_on_engine(name):
    results = play(SCENARIOS[name], make_runner(name))
    bad = [f"{r.no}단계 기대 {r.expected} 실제 {r.actual} {r.note}" for r in results if not r.ok]
    assert not bad, "\n".join(bad)


def test_hard_step8_is_rejected_by_recheck_with_reason():
    runner = make_runner("어려움")
    play(SCENARIOS["어려움"], runner)
    assert runner.application_status("2026306") == "거절"
    assert runner.application_reason("2026306").startswith("승인 직전 검사에서")


def test_hard_team3_has_two_members_when_step11_blocks():
    runner = make_runner("어려움")
    play(SCENARIOS["어려움"], runner)
    assert [s.student_no for s in runner.teams()[3]][:2] == ["2026311", "2026315"]


def test_engine_close_twice_is_blocked():
    runner = make_runner("쉬움")
    assert runner.close().word == "승인"
    assert runner.close().word == "막힘"


def test_engine_vote_on_decided_application_keeps_status():
    runner = make_runner("쉬움")
    runner.apply("2026101", 1)
    runner.apply("2026104", 1)
    assert runner.vote("2026101", "2026104", False).word == "거절"
    assert runner.vote("2026101", "2026104", True).word == "거절"
    assert runner.application_status("2026104") == "거절"


def test_engine_vote_by_non_member_is_blocked():
    runner = make_runner("쉬움")
    runner.apply("2026101", 1)
    runner.apply("2026104", 1)
    assert runner.vote("2026102", "2026104", True).word == "막힘"
