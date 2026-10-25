# 작성: 2026-10-26 00:07 KST
"""부록 시나리오를 DB 서비스에 흘려 메모리 엔진과 같은 결과가 나오는지 본다(마감 전 단계)."""
from dataclasses import replace
from pathlib import Path

import pytest

from teamapp import service
from teamapp.engine import Engine
from teamapp.roster import parse_roster
from teamapp.service import User
from tests.fixtures.runners import DbRunner, EngineRunner
from tests.fixtures.scenarios import SCENARIOS, play

FIX = Path(__file__).parent / "fixtures"
ADMIN = User(1, "admin", "관리자", True)

pytestmark = pytest.mark.db


def before_close(scenario):
    """첫 마감 동작이 나오기 전까지의 단계만 남긴다(마감과 배정은 4단계에서 이어 붙임)."""
    steps = []
    for step in scenario.steps:
        if any(a[0] in ("close", "assign") for a in step.actions):
            break
        steps.append(step)
    return replace(scenario, steps=tuple(steps))


@pytest.mark.parametrize("name", ["쉬움", "중간", "어려움"])
def test_db_matches_engine(db, monkeypatch, name):
    monkeypatch.setenv("ADMIN_PASSWORD", "시험용-관리자")
    service.ensure_admin()
    scenario = before_close(SCENARIOS[name])
    data = (FIX / f"{name}.csv").read_bytes()
    assert service.start_from_roster(ADMIN, data, scenario.team_count).word == "승인"

    db_runner = DbRunner(db)
    engine_runner = EngineRunner(Engine(parse_roster(data), scenario.team_count))
    on_db = play(scenario, db_runner)
    on_engine = play(scenario, engine_runner)
    assert len(on_db) == len(scenario.steps) > 0
    assert [(r.actual, r.ok) for r in on_db] == [(r.actual, r.ok) for r in on_engine]
    assert all(r.ok for r in on_db), [r for r in on_db if not r.ok]

    def numbers(teams):
        return {n: [s.student_no for s in m] for n, m in teams.items()}

    assert numbers(db_runner.teams()) == numbers(engine_runner.teams())
