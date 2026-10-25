# 작성: 2026-10-25 23:55 KST
"""팀이 없는 학생의 완전탐색 배정. 5가지 검사를 모두 통과하는 배정을 가지치기로 찾는다."""
from dataclasses import dataclass
from typing import Mapping, Sequence

from teamapp import rules
from teamapp.config import MAX_TEAM, MIN_TEAM, PL, WP
from teamapp.rules import Student


@dataclass(frozen=True)
class SolveResult:
    assignment: dict[int, list[Student]] | None
    reason: str | None


def _precheck(teams: Mapping[int, Sequence[Student]], free: Sequence[Student]) -> str | None:
    """불가능을 빨리 알아보는 하한 검사. 걸리면 사유를, 아니면 None."""
    if len(free) > sum(MAX_TEAM - len(m) for m in teams.values()):
        return "남은 학생 수가 남은 자리보다 많음"
    if sum(max(0, MIN_TEAM - len(m)) for m in teams.values()) > len(free):
        return "모든 팀을 2명 이상으로 채우기에 학생이 모자람"
    for team_no, members in sorted(teams.items()):
        mains = {m.main_role for m in members}
        for role in (PL, WP):
            if any(rules.can(m, role) for m in members):
                continue
            if not any(rules.can(c, role) and c.main_role not in mains for c in free):
                return f"팀{team_no}에 {role}를 맡을 학생이 없음"
    return None


def solve(teams: Mapping[int, Sequence[Student]], free: Sequence[Student]) -> SolveResult:
    reason = _precheck(teams, free)
    if reason:
        return SolveResult(None, reason)

    members = {n: list(m) for n, m in teams.items()}
    added: dict[int, list[Student]] = {n: [] for n in teams}
    order = sorted(members)

    def feasible_teams(s: Student) -> list[int]:
        return [
            n
            for n in order
            if len(members[n]) < MAX_TEAM and all(m.main_role != s.main_role for m in members[n])
        ]

    def prune(remaining: int) -> bool:
        """지금 상태에서 더 진행해 볼 가치가 있는지."""
        need = 0
        for m in members.values():
            if MAX_TEAM - len(m) < rules.unmet(m):
                return False
            need += max(0, MIN_TEAM - len(m))
        return need <= remaining

    def dfs(rest: list[Student]) -> bool:
        if not rest:
            return all(
                MIN_TEAM <= len(m) <= MAX_TEAM and rules.cover(m) == 2 for m in members.values()
            )
        if not prune(len(rest)):
            return False
        # 들어갈 수 있는 팀이 가장 적은 학생부터 놓는다.
        options = [(len(feasible_teams(s)), i) for i, s in enumerate(rest)]
        count, idx = min(options)
        if count == 0:
            return False
        s = rest[idx]
        others = rest[:idx] + rest[idx + 1 :]
        tried_empty = False
        for n in feasible_teams(s):
            if not members[n]:  # 비어 있는 팀끼리는 서로 같으므로 하나만 시도
                if tried_empty:
                    continue
                tried_empty = True
            members[n].append(s)
            added[n].append(s)
            if dfs(others):
                return True
            members[n].pop()
            added[n].pop()
        return False

    if dfs(list(free)):
        return SolveResult({n: list(a) for n, a in added.items()}, None)
    return SolveResult(None, "모든 조건을 동시에 만족하는 조합이 없음")
