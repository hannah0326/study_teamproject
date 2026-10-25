# 작성: 2026-10-25 23:13 KST
"""시나리오 실행기. 3단계에서 DB 서비스용 실행기를 같은 규약으로 추가한다."""
from teamapp.engine import Engine
from teamapp.rules import Decision
from teamapp.solver import solve


class EngineRunner:
    """Engine 을 시나리오 실행기 규약(apply, vote, close, assign_and_confirm, 조회)에 맞춘다."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def apply(self, student_no, team_no):
        return self.engine.apply(student_no, team_no)

    def vote(self, voter_no, applicant_no, yes):
        return self.engine.vote(voter_no, applicant_no, yes)

    def close(self):
        return self.engine.close()

    def assign_and_confirm(self) -> Decision:
        result = solve(self.engine.teams(), self.engine.unassigned())
        if result.assignment is None:
            return Decision("막힘", result.reason)
        return self.engine.confirm(result.assignment)

    def unassigned(self):
        return self.engine.unassigned()

    def teams(self):
        return self.engine.teams()

    def application_status(self, student_no):
        return self.engine.application_status(student_no)

    def application_reason(self, student_no):
        return self.engine.application_reason(student_no)
