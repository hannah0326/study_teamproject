# 작성: 2026-10-25 23:40 KST
from pathlib import Path

import pytest

from teamapp.roster import RosterError, parse_roster

FIX = Path(__file__).parent / "fixtures"
HEADER = "student_no,name,main_role,sub_roles\n"


def raw(name: str) -> bytes:
    return (FIX / f"{name}.csv").read_bytes()


def csv(*rows: str) -> bytes:
    return (HEADER + "".join(r + "\n" for r in rows)).encode("utf-8")


@pytest.mark.parametrize("name,count", [("쉬움", 8), ("중간", 12), ("어려움", 16)])
def test_parse_three_fixtures_counts(name, count):
    students = parse_roster(raw(name))
    assert len(students) == count
    nos = [s.student_no for s in students]
    assert nos == sorted(nos)
    assert len(set(nos)) == count


def test_parse_bom_and_no_bom_same_result():
    with_bom = raw("쉬움")
    assert with_bom.startswith(b"\xef\xbb\xbf")
    without_bom = with_bom[3:]
    assert parse_roster(with_bom) == parse_roster(without_bom)


def test_parse_reads_roles_from_columns_not_name():
    students = parse_roster(csv("1,학생1(WP;WP),기획자,테스터;발표자"))
    assert students[0].main_role == "기획자"
    assert students[0].sub_roles == ("테스터", "발표자")
    renamed = parse_roster(csv("1,가나다,기획자,테스터;발표자"))
    assert renamed[0].main_role == students[0].main_role
    assert renamed[0].sub_roles == students[0].sub_roles


def test_parse_trailing_blank_line_ignored():
    data = csv("1,가,기획자,") + b"\n\n,,,\n"
    assert len(parse_roster(data)) == 1


def test_parse_empty_sub_roles_gives_empty_tuple():
    s = {x.student_no: x for x in parse_roster(raw("쉬움"))}["2026105"]
    assert s.sub_roles == ()


def test_parse_strips_spaces():
    s = parse_roster(csv(" 7 , 가나 , 기획자 , 테스터 ; 발표자 "))[0]
    assert (s.student_no, s.name, s.main_role, s.sub_roles) == (
        "7", "가나", "기획자", ("테스터", "발표자"))


BAD = {
    "UTF-8 아님": b"\xff\xfe\x00\x00",
    "열 이름 다름": "no,name,main_role,sub_roles\n1,가,기획자,\n".encode(),
    "열 3개": csv("1,가,기획자"),
    "열 5개": csv("1,가,기획자,,"),
    "학번 빈 값": csv(",가,기획자,"),
    "이름 빈 값": csv("1,,기획자,"),
    "학번 중복": csv("1,가,기획자,", "1,나,테스터,"),
    "주 역할 오류": csv("1,가,마법사,"),
    "보조 역할 오류": csv("1,가,기획자,마법사"),
    "보조 3개": csv("1,가,기획자,테스터;발표자;보고서 작성자"),
    "보조에 주 역할": csv("1,가,기획자,기획자"),
    "보조끼리 같음": csv("1,가,기획자,발표자;발표자"),
    "학번 admin": csv("admin,가,기획자,"),
    "학생 0명": HEADER.encode(),
}


@pytest.mark.parametrize("data", BAD.values(), ids=BAD.keys())
def test_parse_errors(data):
    with pytest.raises(RosterError) as e:
        parse_roster(data)
    assert str(e.value)
