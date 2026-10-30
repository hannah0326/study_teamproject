# 작성: 2026-10-26 03:22 KST
"""AI 배정 흐름. 가짜 call 로 1차→2차→3차→직접 배정을 시험한다(실제 호출 없음)."""
import json
import time
from dataclasses import replace
from pathlib import Path

import pytest

from teamapp import assign_flow, rules, solver
from teamapp.ai import AiResult
from teamapp.engine import Engine
from teamapp.roster import parse_roster
from teamapp.rules import Student
from tests.fixtures.runners import EngineRunner
from tests.fixtures.scenarios import HARD, play

FIX = Path(__file__).parent / "fixtures"
MODELS = ("m/first:free", "m/second:free", "m/third:free")


@pytest.fixture(scope="module")
def hard_closed():
    """어려움 시나리오를 마감(14단계)까지 진행한 팀 구성과 팀이 없는 학생."""
    runner = EngineRunner(Engine(parse_roster((FIX / "어려움.csv").read_bytes()), 4))
    assert all(r.ok for r in play(replace(HARD, steps=HARD.steps[:14]), runner))
    return runner.teams(), runner.unassigned()


def answer(assignment) -> str:
    return json.dumps({"teams": {str(n): [s.student_no for s in m] for n, m in assignment.items()}})


def good_text(teams, free) -> str:
    return answer(solver.solve(teams, free).assignment)


class FakeCall:
    """정해 둔 결과를 차례로 돌려주고, 불린 모델을 기록한다."""

    def __init__(self, *results, delay=0.0):
        self.results = list(results)
        self.models = []
        self.delay = delay

    def __call__(self, model, messages):
        self.models.append(model)
        if self.delay:
            time.sleep(self.delay)
        return self.results.pop(0)


def ok(text):
    return AiResult(True, text, None, 1.0)


def fail(error):
    return AiResult(False, None, error, 1.0)


def run(teams, free, call, **kw):
    statuses = []
    kw.setdefault("tick", 0.05)
    result = assign_flow.run(teams, free, call=call, models=MODELS, on_status=statuses.append, **kw)
    return result, statuses


def test_first_model_success_calls_once(hard_closed):
    teams, free = hard_closed
    call = FakeCall(ok(good_text(teams, free)))
    result, _ = run(teams, free, call)
    assert result.source == "ai1" and call.models == [MODELS[0]]
    assert rules.validate_assignment(teams, free, result.assignment) == []
    assert [(a.step, a.model, a.result) for a in result.log] == [(1, MODELS[0], "ok")]


def bad_rule_text(teams, free) -> str:
    return answer({1: list(free)})  # 팀1에 모두 넣음: 인원·역할 규칙 위반


@pytest.mark.parametrize(
    "first, label",
    [
        (fail("empty"), "empty"),
        (fail("http_404"), "http_404"),
        (fail("http_429"), "http_429"),
        (fail("timeout"), "timeout"),
        (ok("배정할 수 없습니다"), "parse_error"),
        ("rule", "rule_violation"),
    ],
    ids=["빈 응답", "404", "429", "120초 초과", "JSON 오류", "규칙 위반"],
)
def test_each_failure_kind_moves_to_next(hard_closed, first, label):
    teams, free = hard_closed
    if first == "rule":
        first = ok(bad_rule_text(teams, free))
    call = FakeCall(first, ok(good_text(teams, free)))
    result, _ = run(teams, free, call)
    assert result.source == "ai2" and call.models == list(MODELS[:2])
    assert result.log[0].result == label
    assert rules.validate_assignment(teams, free, result.assignment) == []


def test_log_keeps_reason_and_answer_head(hard_closed):
    """실패 원인을 나중에 가릴 수 있게: 오류 문구, 해석 실패 이유와 답의 앞부분, 규칙 위반 내용을 남긴다."""
    teams, free = hard_closed
    call = FakeCall(
        AiResult(False, None, "http_429", 1.0, "Rate limit exceeded: free-models-per-day"),
        ok("배정할 수 없습니다. 학생이 너무 많습니다."),
        ok(bad_rule_text(teams, free)),
    )
    result, _ = run(teams, free, call)
    first, second, third = result.log
    assert "free-models-per-day" in first.detail
    assert "JSON" in second.detail and "배정할 수 없습니다" in second.detail
    assert "인원" in third.detail and '"teams"' in third.detail
    assert first.started_at <= second.started_at <= third.started_at
    assert all(len(a.detail) <= 400 for a in result.log)


def test_attempt_line_never_puts_colon_after_model_name():
    """'모델이름:free: …' 처럼 쌍점 사이에 낱말이 오면 화면에서 이모지로 바뀐다(발견한 문제)."""
    line = assign_flow.describe_attempt(
        assign_flow.AttemptLog(1, "m/first:free", "http_429", 2.2, "upstream busy")
    )
    assert line == "1차 모델(m/first:free) — 사용량이 많다며 거절함(429) (2.2초) — upstream busy"
    ok_line = assign_flow.describe_attempt(assign_flow.AttemptLog(2, "m/second:free", "ok", 52.6))
    assert ok_line == "2차 모델(m/second:free) — 성공 (52.6초)"


def test_live_status_has_no_outside_text(hard_closed):
    """진행 안내(마크다운으로 그림)에는 우리가 쓴 문장만 넣고, 바깥에서 온 이유는 기록 줄에만 남긴다."""
    teams, free = hard_closed
    call = FakeCall(AiResult(False, None, "http_429", 1.0, "x:free: busy"), fail("empty"), fail("empty"))
    result, statuses = run(teams, free, call)
    assert not [s for s in statuses if "x:free: busy" in s]
    assert result.log[0].detail == "x:free: busy"


def test_three_failures_use_solver_and_pass_validation(hard_closed):
    teams, free = hard_closed
    call = FakeCall(fail("http_429"), fail("empty"), ok(bad_rule_text(teams, free)))
    result, statuses = run(teams, free, call)
    assert result.source == "solver" and len(call.models) == 3
    assert rules.validate_assignment(teams, free, result.assignment) == []
    assert "앱이 직접 배정함" in result.message
    assert "앱이 직접 배정함" in statuses[-1]
    assert [a.result for a in result.log] == ["http_429", "empty", "rule_violation"]


def test_infeasible_never_calls_ai():
    pl = Student("1", "가", "기획자", ())
    teams = {1: [pl], 2: [Student("2", "나", "기획자", ())]}
    free = [Student("3", "다", "테스터", ()), Student("4", "라", "발표자", ())]  # 웹 프로그래머 후보 없음

    def never(model, messages):
        raise AssertionError("AI를 부르면 안 됨")

    result, statuses = run(teams, free, never)
    assert result.source == "none" and result.assignment is None
    assert result.message.startswith("규칙을 지키는 배정이 없음")
    assert "팀1에 웹 프로그래머를 맡을 학생이 없음" in result.message
    assert statuses and statuses[-1] == result.message


def test_status_messages_show_stage_number(hard_closed):
    teams, free = hard_closed
    call = FakeCall(fail("timeout"), fail("timeout"), fail("timeout"))
    _, statuses = run(teams, free, call)
    waits = [s for s in statuses if "응답을 기다리는 중" in s]
    stages = [s[:2] for s in waits]
    assert stages.index("1차") < stages.index("2차") < stages.index("3차")
    assert all(f"({m})" in " ".join(waits) for m in MODELS)


def test_waiting_updates_elapsed_seconds(hard_closed):
    teams, free = hard_closed
    call = FakeCall(ok(good_text(teams, free)), delay=1.3)
    _, statuses = run(teams, free, call, tick=0.1)
    waits = [s for s in statuses if s.startswith("1차") and "경과" in s]
    assert any("경과 0초" in s for s in waits) and any("경과 1초" in s for s in waits)


def test_total_time_bound(hard_closed):
    teams, free = hard_closed
    call = FakeCall(fail("timeout"), fail("timeout"), fail("timeout"))
    result, _ = run(teams, free, call)
    assert len(call.models) == 3 and result.source == "solver"


def test_hung_call_is_cut_by_flow(hard_closed):
    """호출 함수가 스스로 끝나지 않아도 흐름이 모델마다 제한 시간에서 끊고 넘어간다."""
    teams, free = hard_closed
    call = FakeCall(ok("{}"), ok("{}"), ok("{}"), delay=3)
    start = time.monotonic()
    result, _ = run(teams, free, call, limit=0.3)
    assert result.source == "solver"
    assert [a.result for a in result.log] == ["timeout"] * 3
    assert time.monotonic() - start < 2.5
