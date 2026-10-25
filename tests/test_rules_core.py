# 작성: 2026-10-25 23:10 KST
from teamapp import rules
from tests.helpers import FD, PL, PT, RW, TT, WP, mk


def test_can_main_or_sub():
    s = mk("1", PL, WP)
    assert rules.can(s, PL)
    assert rules.can(s, WP)
    assert not rules.can(s, TT)


def test_cover_pl_main_with_wp_sub_alone_is_1():
    team = [mk("1", PL, WP)]
    assert rules.cover(team) == 1
    assert rules.unmet(team) == 1


def test_cover_two_people_is_2():
    team = [mk("1", PL), mk("2", WP)]
    assert rules.cover(team) == 2
    assert rules.unmet(team) == 0


def test_cover_one_person_both_roles_counts_once():
    assert rules.cover([mk("1", PL, WP)]) == 1


def test_cover_one_with_pl_and_other_with_pl_wp_is_2():
    team = [mk("1", PL), mk("2", FD, PL, WP)]
    assert rules.cover(team) == 2


def test_cover_none_is_0():
    team = [mk("1", TT), mk("2", PT)]
    assert rules.cover(team) == 0
    assert rules.unmet(team) == 2


def test_cover_empty_team_is_0():
    assert rules.cover([]) == 0


def test_main_dup_uses_main_only():
    assert rules.has_main_dup([mk("1", TT), mk("2", TT)])
    assert not rules.has_main_dup([mk("1", TT, RW), mk("2", PT, RW)])
