# 작성: 2026-10-26 00:10 KST
"""연습용 시나리오 3개(쉬움, 중간, 어려움)의 단계와 기대 결과. 학생 N의 학번 = base + N."""
from dataclasses import dataclass
from typing import Callable

from teamapp import rules


@dataclass(frozen=True)
class Step:
    actions: tuple
    expected: tuple[str, ...]  # 동작마다의 결과 첫 단어(마지막이 단계의 판정)
    check: Callable | None = None  # runner -> 어긋나면 사유 문구, 맞으면 None


@dataclass(frozen=True)
class Scenario:
    csv_name: str
    team_count: int
    base: int
    steps: tuple[Step, ...]


@dataclass(frozen=True)
class StepResult:
    no: int
    label: str
    expected: tuple[str, ...]
    actual: tuple[str, ...]
    ok: bool
    note: str


def A(n, team):
    return ("apply", n, team)


def Y(voter, applicant):
    return ("vote", voter, applicant, True)


def N(voter, applicant):
    return ("vote", voter, applicant, False)


CLOSE = ("close",)
ASSIGN = ("assign",)


def S(actions, *expected, check=None):
    return Step(tuple(actions), tuple(expected), check)


def _final(runner):
    if runner.unassigned():
        return "팀이 없는 학생이 남음"
    return "; ".join(rules.validate_assignment(runner.teams(), [], {})) or None


def _no_team(base, *ns):
    def check(runner):
        left = {s.student_no for s in runner.unassigned()}
        missing = [n for n in ns if str(base + n) not in left]
        return f"팀이 없는 학생에 학생{missing} 이(가) 없음" if missing else None

    return check


def _status(base, n, status):
    def check(runner):
        got = runner.application_status(str(base + n))
        return None if got == status else f"학생{n}의 지원 상태가 {got} (기대 {status})"

    return check


def _all(*checks):
    def check(runner):
        for c in checks:
            msg = c(runner)
            if msg:
                return msg
        return None

    return check


def describe(action, base=0) -> str:
    kind = action[0]
    if kind == "apply":
        return f"학생{action[1]}이 팀{action[2]}에 지원"
    if kind == "vote":
        return f"학생{action[1]}이 학생{action[2]}에 {'찬성' if action[3] else '거부'}"
    return "관리자 마감" if kind == "close" else "관리자 배정, 확정"


def play(scenario: Scenario, runner) -> list[StepResult]:
    results = []
    for no, step in enumerate(scenario.steps, start=1):
        words = []
        for act in step.actions:
            kind = act[0]
            if kind == "apply":
                d = runner.apply(str(scenario.base + act[1]), act[2])
            elif kind == "vote":
                d = runner.vote(str(scenario.base + act[1]), str(scenario.base + act[2]), act[3])
            elif kind == "close":
                d = runner.close()
            else:
                d = runner.assign_and_confirm()
            words.append(d.word)
        note = step.check(runner) if step.check else None
        label = ", ".join(describe(a) for a in step.actions)
        ok = tuple(words) == step.expected and note is None
        results.append(StepResult(no, label, step.expected, tuple(words), ok, note or ""))
    return results


EASY = Scenario("쉬움", 3, 2026100, (
    S([A(1, 1), A(2, 2), A(3, 3)], "승인", "승인", "승인"),
    S([A(4, 1), Y(1, 4)], "대기", "승인"),
    S([A(5, 2), Y(2, 5)], "대기", "승인"),
    S([A(7, 1), Y(1, 7), N(4, 7)], "대기", "대기", "거절"),
    S([A(6, 3), Y(3, 6)], "대기", "승인"),
    S([CLOSE, ASSIGN], "승인", "승인", check=_final),
))

MEDIUM_BASE = 2026200
MEDIUM = Scenario("중간", 4, MEDIUM_BASE, (
    S([A(1, 1)], "승인"),
    S([A(5, 1), Y(1, 5)], "대기", "승인"),
    S([A(2, 1)], "막힘"),
    S([A(6, 2)], "승인"),
    S([A(9, 2), Y(6, 9)], "대기", "승인"),
    S([A(10, 2), Y(6, 10), N(9, 10)], "대기", "대기", "거절"),
    S([A(3, 3), A(11, 4)], "승인", "승인"),
    S([A(12, 4), A(12, 3)], "대기", "막힘"),
    S([CLOSE], "승인", check=_all(_status(MEDIUM_BASE, 12, "거절"), _no_team(MEDIUM_BASE, 3, 11))),
    S([A(2, 3)], "막힘"),
    S([ASSIGN], "승인", check=_final),
))

HARD_BASE = 2026300


def _hard_close_check(runner):
    msg = _all(_status(HARD_BASE, 13, "거절"), _no_team(HARD_BASE, 10))(runner)
    if msg:
        return msg
    n = len(runner.unassigned())
    return None if n == 8 else f"팀이 없는 학생이 {n}명 (기대 8명)"


HARD = Scenario("어려움", 4, HARD_BASE, (
    S([A(1, 1)], "승인"),
    S([A(4, 1), Y(1, 4)], "대기", "승인"),
    S([A(7, 1), Y(1, 7), Y(4, 7)], "대기", "대기", "승인"),
    S([A(2, 2)], "승인"),
    S([A(8, 2), Y(2, 8)], "대기", "승인"),
    S([A(5, 2), A(6, 2)], "대기", "대기"),
    S([Y(2, 5), Y(8, 5)], "대기", "승인"),
    S([Y(2, 6), Y(8, 6), Y(5, 6)], "대기", "대기", "거절"),
    S([A(11, 3)], "승인"),
    S([A(15, 3), Y(11, 15)], "대기", "승인"),
    S([A(14, 3)], "막힘"),
    S([A(10, 4)], "승인"),
    S([A(13, 1), Y(1, 13)], "대기", "대기"),
    S([CLOSE], "승인", check=_hard_close_check),
    S([ASSIGN], "승인", check=_final),
))

SCENARIOS = {"쉬움": EASY, "중간": MEDIUM, "어려움": HARD}
