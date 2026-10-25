# 작성: 2026-10-25 23:11 KST
"""팀 규칙 판정. DB와 화면에 의존하지 않는 순수 함수만 둔다."""
from dataclasses import dataclass
from typing import Mapping, Sequence

from teamapp.config import MAX_TEAM, MIN_TEAM, PL, WP

REASON_FULL = "팀이 꽉 참"
REASON_DUP = "같은 주 역할의 팀원이 있음"
REASON_HAS_TEAM = "이미 팀이 있음"
REASON_PENDING = "결과를 기다리는 지원이 있음"
REASON_CLOSED = "모집이 마감됨"
REASON_SLOT = "필수 포함 역할을 맡을 학생의 자리가 모자람"


@dataclass(frozen=True)
class Student:
    student_no: str
    name: str
    main_role: str
    sub_roles: tuple[str, ...]


def can(s: Student, role: str) -> bool:
    """주 역할이 role 이거나 보조 역할에 role 이 있으면 맡을 수 있다."""
    return s.main_role == role or role in s.sub_roles


def cover(members: Sequence[Student]) -> int:
    """필수 포함 역할(PL, WP)을 서로 다른 사람이 맡을 수 있는 개수(0~2)."""
    for a in members:
        for b in members:
            if a is not b and can(a, PL) and can(b, WP):
                return 2
    if any(can(m, PL) or can(m, WP) for m in members):
        return 1
    return 0


def unmet(members: Sequence[Student]) -> int:
    return 2 - cover(members)


def has_main_dup(members: Sequence[Student]) -> bool:
    mains = [m.main_role for m in members]
    return len(mains) != len(set(mains))


@dataclass(frozen=True)
class Decision:
    """결과 안내의 첫 단어(승인, 대기, 거절, 막힘)와 이유."""

    word: str
    reason: str


def _team_problem(members: Sequence[Student], applicant: Student) -> str | None:
    """지원자가 들어간 뒤의 팀을 정원, 주 역할 중복, 필수 포함 역할 자리 순으로 검사."""
    if len(members) >= MAX_TEAM:
        return REASON_FULL
    if any(m.main_role == applicant.main_role for m in members):
        return REASON_DUP
    spare = MAX_TEAM - (len(members) + 1)
    if spare < unmet([*members, applicant]):
        return REASON_SLOT
    return None


def check_apply(
    members: Sequence[Student],
    applicant: Student,
    *,
    closed: bool,
    has_team: bool,
    has_pending: bool,
) -> str | None:
    """지원 가능 검사. 처음 걸린 이유를 돌려주고, 통과하면 None."""
    if closed:
        return REASON_CLOSED
    if has_team:
        return REASON_HAS_TEAM
    if has_pending:
        return REASON_PENDING
    return _team_problem(members, applicant)


def recheck(members: Sequence[Student], applicant: Student) -> str | None:
    """승인 직전 재검사. 넘겨 받은 현재 팀원 기준으로 다시 검사한다."""
    return _team_problem(members, applicant)


def decide_apply(
    members: Sequence[Student],
    applicant: Student,
    *,
    closed: bool,
    has_team: bool,
    has_pending: bool,
) -> Decision:
    reason = check_apply(
        members, applicant, closed=closed, has_team=has_team, has_pending=has_pending
    )
    if reason:
        return Decision("막힘", reason)
    if not members:
        return Decision("승인", "")
    return Decision("대기", "")


def decide_vote(
    members: Sequence[Student],
    votes: Mapping[str, bool],
    applicant: Student,
    voter: Student,
    yes: bool,
    *,
    status: str,
) -> Decision:
    """투표 한 건의 결과. votes 는 이번 표를 뺀 학번→찬성 여부."""
    if status != "대기":
        return Decision(status, "이미 결정된 지원")
    if not yes:
        return Decision("거절", "팀원이 거부함")
    pending = [
        m
        for m in members
        if m.student_no != voter.student_no and votes.get(m.student_no) is not True
    ]
    if pending:
        return Decision("대기", "")
    problem = recheck(members, applicant)
    if problem:
        return Decision("거절", f"승인 직전 검사에서 {problem}")
    return Decision("승인", "")


def validate_assignment(
    teams: Mapping[int, Sequence[Student]],
    free: Sequence[Student],
    assignment: Mapping[int, Sequence[Student]],
) -> list[str]:
    """배정안의 5가지 검사. teams 는 지금 팀원, assignment 는 팀별로 새로 들어가는 학생.

    어긴 것의 문구 목록을 돌려주고, 빈 목록이면 통과다.
    """
    problems: list[str] = []
    free_nos = {s.student_no for s in free}
    placed: dict[str, int] = {}
    for team_no, added in assignment.items():
        if team_no not in teams:
            problems.append(f"없는 팀 {team_no} 에 배정함")
            continue
        for s in added:
            if s.student_no not in free_nos:
                problems.append(f"{s.student_no} 은(는) 이미 팀이 있는 학생이라 옮길 수 없음")
            if s.student_no in placed:
                problems.append(f"{s.student_no} 이(가) 두 팀에 배정됨")
            placed[s.student_no] = team_no
    missing = sorted(free_nos - placed.keys())
    if missing:
        problems.append("배정되지 않은 학생이 있음: " + ", ".join(missing))
    for team_no, current in teams.items():
        members = [*current, *assignment.get(team_no, [])]
        if not MIN_TEAM <= len(members) <= MAX_TEAM:
            problems.append(f"팀{team_no} 인원이 2~4명이 아님({len(members)}명)")
        if has_main_dup(members):
            problems.append(f"팀{team_no} 에 같은 주 역할이 있음")
        if cover(members) < 2:
            problems.append(f"팀{team_no} 의 필수 포함 역할(기획자, 웹 프로그래머)이 채워지지 않음")
    return problems
