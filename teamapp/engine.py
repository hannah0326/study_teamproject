# 작성: 2026-10-25 23:13 KST
"""메모리 상태에서 지원, 투표, 마감을 처리하는 엔진. 시험과 시나리오 재생용이며 규칙은 rules 를 부른다."""
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from teamapp import rules
from teamapp.rules import Decision, Student


@dataclass
class _Application:
    applicant: Student
    team_no: int
    status: str = "대기"
    reason: str = ""
    votes: dict[str, bool] = field(default_factory=dict)


class Engine:
    def __init__(self, students: Sequence[Student], team_count: int):
        self._students = {s.student_no: s for s in students}
        self._teams: dict[int, list[Student]] = {n: [] for n in range(1, team_count + 1)}
        self._apps: list[_Application] = []
        self.closed = False
        self.confirmed = False

    # ---- 조회 ----
    def teams(self) -> dict[int, list[Student]]:
        return {n: list(m) for n, m in self._teams.items()}

    def unassigned(self) -> list[Student]:
        in_team = {s.student_no for m in self._teams.values() for s in m}
        return sorted(
            (s for s in self._students.values() if s.student_no not in in_team),
            key=lambda s: s.student_no,
        )

    def application_status(self, student_no: str) -> str | None:
        app = self._latest(student_no)
        return app.status if app else None

    def application_reason(self, student_no: str) -> str | None:
        app = self._latest(student_no)
        return app.reason if app else None

    # ---- 동작 ----
    def apply(self, student_no: str, team_no: int) -> Decision:
        applicant = self._students[student_no]
        decision = rules.decide_apply(
            self._teams[team_no],
            applicant,
            closed=self.closed,
            has_team=self._has_team(student_no),
            has_pending=self._pending(student_no) is not None,
        )
        if decision.word == "막힘":
            return decision
        app = _Application(applicant, team_no)
        self._apps.append(app)
        if decision.word == "승인":
            self._approve(app)
        return decision

    def vote(self, voter_no: str, applicant_no: str, yes: bool) -> Decision:
        app = self._pending(applicant_no) or self._latest(applicant_no)
        if app is None:
            return Decision("막힘", "지원이 없음")
        members = self._teams[app.team_no]
        voter = self._students[voter_no]
        if app.status == "대기" and (
            all(m.student_no != voter_no for m in members) or voter_no in app.votes
        ):
            return Decision("막힘", "투표할 자격이 없음")
        decision = rules.decide_vote(
            members, app.votes, app.applicant, voter, yes, status=app.status
        )
        if app.status != "대기":
            return decision
        app.votes[voter_no] = yes
        if decision.word == "승인":
            self._approve(app)
        elif decision.word == "거절":
            app.status, app.reason = "거절", decision.reason
        return decision

    def close(self) -> Decision:
        if self.closed:
            return Decision("막힘", "이미 마감함")
        self.closed = True
        for app in self._apps:
            if app.status == "대기":
                app.status, app.reason = "거절", "모집 마감"
        for n, members in self._teams.items():
            if len(members) == 1:
                self._teams[n] = []
        return Decision("승인", "모집을 마감함")

    def confirm(self, assignment: Mapping[int, Sequence[Student]]) -> Decision:
        problems = rules.validate_assignment(self._teams, self.unassigned(), assignment)
        if problems:
            return Decision("막힘", problems[0])
        for n, added in assignment.items():
            self._teams[n].extend(added)
        self.confirmed = True
        return Decision("승인", "배정안을 확정함")

    # ---- 내부 ----
    def _has_team(self, student_no: str) -> bool:
        return any(s.student_no == student_no for m in self._teams.values() for s in m)

    def _pending(self, student_no: str) -> _Application | None:
        return next(
            (a for a in self._apps if a.applicant.student_no == student_no and a.status == "대기"),
            None,
        )

    def _latest(self, student_no: str) -> _Application | None:
        mine = [a for a in self._apps if a.applicant.student_no == student_no]
        return mine[-1] if mine else None

    def _approve(self, app: _Application) -> None:
        self._teams[app.team_no].append(app.applicant)
        app.status = "승인"
