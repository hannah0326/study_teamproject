# 작성: 2026-10-25 23:23 KST
"""DB 위의 서비스 층. 규칙은 rules, 배정은 solver 를 부르고 이 파일은 저장과 권한만 맡는다."""
from dataclasses import dataclass

import bcrypt
import psycopg

from teamapp import config, db
from teamapp.roster import RosterError, parse_roster
from teamapp import rules
from teamapp.rules import Decision, Student

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


# ---- 지원과 투표 ----
REASON_TAKEN = "먼저 도착한 학생이 자리를 차지함"
REASON_RELOGIN = "명단이 바뀌어 다시 로그인해야 함"
_SUB_ROLES = (
    "(select coalesce(array_agg(r.role order by r.role), '{}') "
    "from tf_student_sub_roles r where r.student_id = s.id)"
)


def _student(row) -> Student:
    return Student(row[0], row[1], row[2], tuple(row[3]))


def _signed_in(conn, actor: User) -> bool:
    """로그인할 때 받은 계정이 아직 있는지. 명단을 다시 올리면 학생 계정은 새 번호로 다시 만들어진다."""
    return conn.execute(
        "select 1 from tf_students where id = %s and student_no = %s", (actor.id, actor.student_no)
    ).fetchone() is not None


def _flag(conn, key: str) -> bool:
    row = conn.execute("select value from tf_settings where key = %s", (key,)).fetchone()
    return row is not None and row[0] == "1"


def _team_no(name: str) -> int:
    return int(name.removeprefix("팀"))


def _members(conn, team_id: int) -> list[Student]:
    rows = conn.execute(
        f"select s.student_no, s.name, s.main_role, {_SUB_ROLES} "
        "from tf_members m join tf_students s on s.id = m.student_id "
        "where m.team_id = %s order by m.slot_no",
        (team_id,),
    ).fetchall()
    return [_student(r) for r in rows]


def _load_student(conn, student_id: int) -> Student:
    row = conn.execute(
        f"select s.student_no, s.name, s.main_role, {_SUB_ROLES} from tf_students s where s.id = %s",
        (student_id,),
    ).fetchone()
    return _student(row)


def free_slot(conn, team_id: int) -> int:
    """팀에서 비어 있는 가장 작은 자리 번호. 가득 차면 5를 돌려주고 DB 제약이 막는다."""
    used = {r[0] for r in conn.execute("select slot_no from tf_members where team_id = %s", (team_id,))}
    return next((n for n in range(1, config.MAX_TEAM + 1) if n not in used), config.MAX_TEAM + 1)


def _decide(conn, app_id: int, decision: Decision) -> None:
    conn.execute(
        "update tf_applications set status = %s, reason = %s, decided_at = now() where id = %s",
        (decision.word, decision.reason, app_id),
    )


def _approve(conn, app_id: int, team_id: int, student_id: int) -> Decision:
    """자리를 배정하고 승인으로 기록한다. 유일성 제약에 걸리면 거절로 기록한다."""
    try:
        with conn.transaction():  # 실패해도 바깥 트랜잭션은 살리는 세이브포인트
            conn.execute(
                "insert into tf_members (team_id, slot_no, student_id) values (%s, %s, %s)",
                (team_id, free_slot(conn, team_id), student_id),
            )
    except (psycopg.errors.UniqueViolation, psycopg.errors.CheckViolation):
        decision = Decision("거절", REASON_TAKEN)
    else:
        decision = Decision("승인", "")
    _decide(conn, app_id, decision)
    return decision


def apply(actor: User, team_no: int) -> Decision:
    """actor 가 team_no 팀에 지원한다. 막힘은 기록하지 않고, 빈 팀이면 바로 승인한다."""
    if actor is None or actor.is_admin:
        return Decision("막힘", "학생만 쓸 수 있는 기능임")
    with db.connection() as conn:
        if not _signed_in(conn, actor):
            return Decision("막힘", REASON_RELOGIN)
        team = conn.execute(
            "select id from tf_teams where name = %s for update", (f"팀{team_no}",)
        ).fetchone()
        if team is None:
            return Decision("막힘", "없는 팀임")
        team_id = team[0]
        applicant = _load_student(conn, actor.id)
        decision = rules.decide_apply(
            _members(conn, team_id),
            applicant,
            closed=_flag(conn, "closed"),
            has_team=conn.execute(
                "select 1 from tf_members where student_id = %s", (actor.id,)
            ).fetchone() is not None,
            has_pending=conn.execute(
                "select 1 from tf_applications where student_id = %s and status = '대기'",
                (actor.id,),
            ).fetchone() is not None,
        )
        if decision.word == "막힘":
            return decision
        try:
            with conn.transaction():
                (app_id,) = conn.execute(
                    "insert into tf_applications (team_id, student_id, status) "
                    "values (%s, %s, '대기') returning id",
                    (team_id, actor.id),
                ).fetchone()
        except psycopg.errors.UniqueViolation:  # 같은 학생의 동시 지원
            return Decision("막힘", rules.REASON_PENDING)
        if decision.word == "승인":
            return _approve(conn, app_id, team_id, actor.id)
        return decision


def vote(actor: User, applicant_no: str, yes: bool) -> Decision:
    """actor(지원한 팀의 팀원)가 applicant_no 의 지원에 찬성/거부한다."""
    if actor is None or actor.is_admin:
        return Decision("막힘", "학생만 쓸 수 있는 기능임")
    with db.connection() as conn:
        if not _signed_in(conn, actor):
            return Decision("막힘", REASON_RELOGIN)
        found = conn.execute(
            "select a.team_id from tf_applications a join tf_students s on s.id = a.student_id "
            "where s.student_no = %s order by (a.status = '대기') desc, a.id desc limit 1",
            (applicant_no,),
        ).fetchone()
        if found is None:
            return Decision("막힘", "지원이 없음")
        team_id = found[0]
        conn.execute("select id from tf_teams where id = %s for update", (team_id,))
        # 잠근 뒤에 다시 읽는다: 기다리는 사이 다른 표로 결정됐을 수 있다
        app_id, applicant_id, status, reason = conn.execute(
            "select a.id, a.student_id, a.status, coalesce(a.reason, '') "
            "from tf_applications a join tf_students s on s.id = a.student_id "
            "where s.student_no = %s and a.team_id = %s order by (a.status = '대기') desc, a.id desc "
            "limit 1",
            (applicant_no, team_id),
        ).fetchone()
        if status != "대기":
            return Decision(status, reason or "이미 결정된 지원")
        members = _members(conn, team_id)
        voter = _load_student(conn, actor.id)
        if all(m.student_no != voter.student_no for m in members):
            return Decision("막힘", "투표할 자격이 없음")
        votes = {
            r[0]: r[1] == "찬성"
            for r in conn.execute(
                "select s.student_no, v.vote from tf_votes v join tf_students s on s.id = v.voter_id "
                "where v.application_id = %s",
                (app_id,),
            )
        }
        if voter.student_no in votes:
            return Decision("막힘", "이미 투표함")
        decision = rules.decide_vote(
            members, votes, _load_student(conn, applicant_id), voter, yes, status=status
        )
        conn.execute(
            "insert into tf_votes (application_id, voter_id, vote) values (%s, %s, %s)",
            (app_id, actor.id, "찬성" if yes else "거부"),
        )
        if decision.word == "승인":
            return _approve(conn, app_id, team_id, applicant_id)
        if decision.word == "거절":
            _decide(conn, app_id, decision)
        return decision


# ---- 현황 조회 ----
@dataclass(frozen=True)
class PendingApp:
    applicant: Student
    team_no: int
    votes: dict[str, bool]  # 투표한 팀원 학번 → 찬성 여부


@dataclass(frozen=True)
class MyApp:
    team_no: int
    status: str
    reason: str


@dataclass(frozen=True)
class Snapshot:
    closed: bool
    confirmed: bool
    teams: dict[int, list[Student]]
    pending: list[PendingApp]
    my_votes: dict[str, bool]  # 내가 투표한 대기 지원 지원자 학번 → 찬성 여부
    my_team: int | None
    my_app: MyApp | None  # 내 가장 최근 지원
    signed_in: bool = True  # 로그인한 계정이 아직 DB에 있는지(명단을 다시 올리면 없어짐)


def snapshot(actor: User) -> Snapshot:
    """한 화면에 필요한 값을 한 연결에서 읽는다."""
    with db.connection() as conn:
        teams: dict[int, list[Student]] = {
            _team_no(r[0]): [] for r in conn.execute("select name from tf_teams order by id")
        }
        my_team = None
        for row in conn.execute(
            f"select t.name, s.id, s.student_no, s.name, s.main_role, {_SUB_ROLES} "
            "from tf_members m join tf_teams t on t.id = m.team_id "
            "join tf_students s on s.id = m.student_id order by t.id, m.slot_no"
        ):
            no = _team_no(row[0])
            teams[no].append(_student(row[2:]))
            if row[1] == actor.id:
                my_team = no
        votes: dict[int, dict[str, bool]] = {}
        my_votes: dict[str, bool] = {}
        for app_id, voter_no, voter_id, vote_, applicant_no in conn.execute(
            "select v.application_id, vs.student_no, vs.id, v.vote, ap.student_no "
            "from tf_votes v join tf_applications a on a.id = v.application_id "
            "join tf_students vs on vs.id = v.voter_id "
            "join tf_students ap on ap.id = a.student_id where a.status = '대기'"
        ):
            votes.setdefault(app_id, {})[voter_no] = vote_ == "찬성"
            if voter_id == actor.id:
                my_votes[applicant_no] = vote_ == "찬성"
        pending = [
            PendingApp(_student(r[2:]), _team_no(r[1]), votes.get(r[0], {}))
            for r in conn.execute(
                f"select a.id, t.name, s.student_no, s.name, s.main_role, {_SUB_ROLES} "
                "from tf_applications a join tf_teams t on t.id = a.team_id "
                "join tf_students s on s.id = a.student_id where a.status = '대기' order by a.id"
            )
        ]
        mine = conn.execute(
            "select t.name, a.status, coalesce(a.reason, '') from tf_applications a "
            "join tf_teams t on t.id = a.team_id where a.student_id = %s order by a.id desc limit 1",
            (actor.id,),
        ).fetchone()
        return Snapshot(
            closed=_flag(conn, "closed"),
            confirmed=_flag(conn, "confirmed"),
            teams=teams,
            pending=pending,
            my_votes=my_votes,
            my_team=my_team,
            my_app=MyApp(_team_no(mine[0]), mine[1], mine[2]) if mine else None,
            signed_in=_signed_in(conn, actor),
        )


def unassigned() -> list[Student]:
    """팀이 없는 학생(관리자 제외)을 학번 순으로."""
    with db.connection() as conn:
        rows = conn.execute(
            f"select s.student_no, s.name, s.main_role, {_SUB_ROLES} from tf_students s "
            "where not s.is_admin and not exists (select 1 from tf_members m where m.student_id = s.id) "
            "order by s.student_no"
        ).fetchall()
    return [_student(r) for r in rows]
