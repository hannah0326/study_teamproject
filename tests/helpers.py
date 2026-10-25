# 작성: 2026-10-25 23:22 KST
"""시험용 학생 만들기 도우미."""
from teamapp.rules import Student

PL = "기획자"
WP = "웹 프로그래머"
FD = "프론트엔드 디자이너"
TT = "테스터"
RW = "보고서 작성자"
PT = "발표자"


def mk(no: str, main: str, *subs: str) -> Student:
    return Student(student_no=no, name=f"이름{no}", main_role=main, sub_roles=tuple(subs))
