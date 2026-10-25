# 작성: 2026-10-25 23:11 KST
"""명단 CSV 읽기와 검증. 역할은 main_role, sub_roles 열에서만 읽는다."""
import csv
import io

from teamapp.config import ROLES
from teamapp.rules import Student

HEADER = ["student_no", "name", "main_role", "sub_roles"]


class RosterError(ValueError):
    """메시지가 곧 화면에 보일 '막힘' 이유."""


def parse_roster(data: bytes) -> list[Student]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise RosterError("UTF-8 형식의 파일이 아님") from None

    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not rows or [c.strip() for c in rows[0]] != HEADER:
        raise RosterError("열 이름이 student_no,name,main_role,sub_roles 와 다름")

    students: list[Student] = []
    seen: set[str] = set()
    for line, row in enumerate(rows[1:], start=2):
        if len(row) != len(HEADER):
            raise RosterError(f"{line}번째 줄의 열 수가 {len(HEADER)}개가 아님")
        no, name, main, subs_text = (c.strip() for c in row)
        if not no or not name:
            raise RosterError(f"{line}번째 줄의 학번이나 이름이 비어 있음")
        if no == "admin":
            raise RosterError("학번 admin 은 쓸 수 없음")
        if no in seen:
            raise RosterError(f"학번 {no} 이(가) 중복됨")
        seen.add(no)
        if main not in ROLES:
            raise RosterError(f"{line}번째 줄의 주 역할이 6개 역할이 아님")
        subs = tuple(s.strip() for s in subs_text.split(";") if s.strip())
        if any(s not in ROLES for s in subs):
            raise RosterError(f"{line}번째 줄의 보조 역할이 6개 역할이 아님")
        if len(subs) > 2:
            raise RosterError(f"{line}번째 줄의 보조 역할이 3개 이상임")
        if main in subs:
            raise RosterError(f"{line}번째 줄의 보조 역할에 주 역할이 들어 있음")
        if len(set(subs)) != len(subs):
            raise RosterError(f"{line}번째 줄의 보조 역할이 서로 같음")
        students.append(Student(no, name, main, subs))

    if not students:
        raise RosterError("학생이 한 명도 없음")
    return students
