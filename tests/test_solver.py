# 작성: 2026-10-25 23:12 KST
import time
from pathlib import Path

from teamapp import rules
from teamapp.roster import parse_roster
from teamapp.solver import solve
from tests.helpers import FD, PL, PT, RW, TT, WP, mk

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return {s.student_no: s for s in parse_roster((FIX / f"{name}.csv").read_bytes())}


# ---- validate_assignment ----

def _base():
    teams = {1: [mk("1", PL)], 2: [mk("2", WP)]}
    s3, s4 = mk("3", TT, WP), mk("4", FD, PL)
    return teams, [s3, s4], s3, s4


def test_validate_ok():
    teams, free, s3, s4 = _base()
    assert rules.validate_assignment(teams, free, {1: [s3], 2: [s4]}) == []


def test_validate_catches_each_of_five():
    teams, free, s3, s4 = _base()
    v = rules.validate_assignment
    assert any("배정되지 않은" in m for m in v(teams, free, {1: [s3]}))  # ①
    assert any("두 팀" in m for m in v(teams, free, {1: [s3, s4], 2: [s4]}))  # ②
    assert any("2~4명" in m for m in v(teams, free, {1: [s3, s4], 2: []}))  # ③
    dup = mk("5", WP, PL)
    assert any("주 역할" in m for m in v(teams, [dup], {1: [], 2: [dup]}))  # ④
    plain3, plain4 = mk("6", TT), mk("7", FD)
    msgs = v(teams, [plain3, plain4], {1: [plain3], 2: [plain4]})
    assert any("필수 포함 역할" in m for m in msgs)  # ⑤


def test_validate_does_not_allow_moving_existing_member():
    teams, free, s3, s4 = _base()
    moved = teams[2][0]
    msgs = rules.validate_assignment(teams, free, {1: [s3, moved], 2: [s4]})
    assert any("팀이 있는 학생" in m for m in msgs)


# ---- solve ----

def test_solve_hard_after_close():
    st = load("어려움")
    pick = lambda *ns: [st[f"2026{300 + n}"] for n in ns]
    teams = {1: pick(1, 4, 7), 2: pick(2, 5, 8), 3: pick(11, 15), 4: []}
    free = pick(3, 6, 9, 10, 12, 13, 14, 16)
    result = solve(teams, free)
    assert result.assignment is not None and result.reason is None
    assert rules.validate_assignment(teams, free, result.assignment) == []


def test_solve_reason_too_many_students_for_slots():
    teams = {1: [mk("1", PL), mk("2", WP), mk("3", FD)]}
    r = solve(teams, [mk("4", TT), mk("5", RW)])
    assert r.assignment is None and "자리" in r.reason


def test_solve_reason_too_few_students_for_min_team():
    r = solve({1: [], 2: []}, [mk("1", PL), mk("2", WP), mk("3", TT)])
    assert r.assignment is None and "2명 이상" in r.reason


def test_solve_reason_names_team_and_role_without_candidate():
    teams = {1: [mk("1", PL), mk("2", WP)], 2: [mk("3", PL)]}
    r = solve(teams, [mk("4", TT), mk("5", FD)])
    assert r.assignment is None
    assert "팀2" in r.reason and "웹 프로그래머" in r.reason


def test_solve_reason_other():
    free = [mk("1", PL, WP), mk("2", PL, WP)]  # 둘 다 주 역할이 같아 한 팀에 못 들어감
    r = solve({1: []}, free)
    assert r.assignment is None and "조합이 없음" in r.reason


def test_solve_more_teams_than_students():
    students = list(load("쉬움").values())
    r = solve({n: [] for n in range(1, 11)}, students)
    assert r.assignment is None and r.reason


def test_solve_16_students_4_teams_fast_feasible():
    students = list(load("어려움").values())
    teams = {n: [] for n in range(1, 5)}
    t0 = time.perf_counter()
    r = solve(teams, students)
    assert time.perf_counter() - t0 < 1
    assert r.assignment is not None
    assert rules.validate_assignment(teams, students, r.assignment) == []


def test_solve_16_students_4_teams_fast_infeasible_by_search():
    # 주 역할이 둘뿐이라 팀마다 최대 2명 → 16명은 들어갈 수 없음(하한 검사로는 안 걸림)
    students = [mk(str(i), PL if i < 8 else TT, WP) for i in range(16)]
    teams = {n: [] for n in range(1, 5)}
    t0 = time.perf_counter()
    r = solve(teams, students)
    assert time.perf_counter() - t0 < 1
    assert r.assignment is None and r.reason


def test_solve_16_students_without_wp_is_fast_infeasible():
    students = [s for s in load("어려움").values() if not rules.can(s, WP)]
    t0 = time.perf_counter()
    r = solve({n: [] for n in range(1, 5)}, students)
    assert time.perf_counter() - t0 < 1
    assert r.assignment is None
