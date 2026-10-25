# 작성: 2026-10-25 23:23 KST
"""DB 위의 서비스 층. 규칙은 rules, 배정은 solver 를 부르고 이 파일은 저장과 권한만 맡는다."""
from dataclasses import dataclass

import bcrypt

from teamapp import config, db
from teamapp.roster import RosterError, parse_roster
from teamapp.rules import Decision

BCRYPT_ROUNDS = 10
ADMIN_NO = "admin"
STUDENT_PASSWORD = "1234"
TEAM_COUNT_RANGE = (1, 10)
_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt(BCRYPT_ROUNDS)).decode()


@dataclass(frozen=True)
class User:
    id: int
    student_no: str
    name: str
    is_admin: bool


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def require_admin(actor: User | None) -> None:
    """관리자 기능은 서버 쪽에서 매번 호출한 사람이 관리자인지 확인한다."""
    if actor is None or not actor.is_admin:
        raise PermissionError("관리자만 쓸 수 있는 기능임")


def ensure_admin() -> None:
    """ADMIN_PASSWORD 로 admin 계정을 만들거나 비밀번호 해시를 갱신한다."""
    password = config.get_secret("ADMIN_PASSWORD")
    if not password:
        raise RuntimeError("관리자 비밀번호가 설정되지 않음")
    with db.connection() as conn:
        conn.execute(
            "insert into tf_students (student_no, name, main_role, password_hash, is_admin) "
            "values (%s, '관리자', null, %s, true) "
            "on conflict (student_no) do update set password_hash = excluded.password_hash, "
            "is_admin = true",
            (ADMIN_NO, hash_password(password)),
        )


def login(student_no: str, password: str) -> User | None:
    """학번과 비밀번호가 모두 맞아야 User 를 돌려준다. 어느 쪽이 틀렸는지는 알리지 않는다."""
    no = (student_no or "").strip()
    with db.connection() as conn:
        row = conn.execute(
            "select id, student_no, name, is_admin, password_hash from tf_students "
            "where student_no = %s",
            (no,),
        ).fetchone()
    if row is None:
        verify_password(password or "", _DUMMY_HASH)  # 학번 유무로 응답 시간이 달라지지 않게
        return None
    if not verify_password(password or "", row[4]):
        return None
    return User(row[0], row[1], row[2], row[3])


def start_from_roster(actor: User | None, data: bytes, team_count: int) -> Decision:
    """명단 CSV와 팀 수로 처음 상태를 만든다. 검증에 실패하면 기존 상태를 바꾸지 않는다."""
    require_admin(actor)
    low, high = TEAM_COUNT_RANGE
    if not low <= team_count <= high:
        return Decision("막힘", f"팀 수는 {low}~{high} 사이여야 함")
    try:
        students = parse_roster(data)
    except RosterError as e:
        return Decision("막힘", str(e))

    with db.connection() as conn:  # 한 트랜잭션: 중간에 실패하면 모두 되돌린다
        conn.execute(
            "truncate tf_votes, tf_applications, tf_members, tf_settings, "
            "tf_student_sub_roles, tf_teams restart identity cascade"
        )
        conn.execute("delete from tf_students where not is_admin")
        for s in students:
            (sid,) = conn.execute(
                "insert into tf_students (student_no, name, main_role, password_hash) "
                "values (%s, %s, %s, %s) returning id",
                (s.student_no, s.name, s.main_role, hash_password(STUDENT_PASSWORD)),
            ).fetchone()
            for role in s.sub_roles:
                conn.execute("insert into tf_student_sub_roles values (%s, %s)", (sid, role))
        for n in range(1, team_count + 1):
            conn.execute("insert into tf_teams (name) values (%s)", (f"팀{n}",))
        conn.execute("insert into tf_settings values ('roster_loaded', '1')")
    return Decision("승인", f"명단을 올림: 학생 {len(students)}명, 팀 {team_count}개")
