# 작성: 2026-10-25 23:13 KST
"""시나리오 실행기. 3단계에서 DB 서비스용 실행기를 같은 규약으로 추가한다."""
from teamapp.engine import Engine
from teamapp.rules import Decision
from teamapp.solver import solve


class EngineRunner:
    """Engine 을 시나리오 실행기 규약(apply, vote, close, assign_and_confirm, 조회)에 맞춘다."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def apply(self, student_no, team_no):
        return self.engine.apply(student_no, team_no)

    def vote(self, voter_no, applicant_no, yes):
        return self.engine.vote(voter_no, applicant_no, yes)

    def close(self):
        return self.engine.close()

    def assign_and_confirm(self) -> Decision:
        result = solve(self.engine.teams(), self.engine.unassigned())
        if result.assignment is None:
            return Decision("막힘", result.reason)
        return self.engine.confirm(result.assignment)

    def unassigned(self):
        return self.engine.unassigned()

    def teams(self):
        return self.engine.teams()

    def application_status(self, student_no):
        return self.engine.application_status(student_no)

    def application_reason(self, student_no):
        return self.engine.application_reason(student_no)


class DbRunner:
    """DB 서비스를 시나리오 실행기 규약에 맞춘다. 학번으로 DB의 학생을 찾아 그 사람으로 호출한다."""

    def __init__(self, db_module):
        from teamapp import service

        self.db = db_module
        self.service = service
        self._users = {}

    def user(self, student_no: str):
        if student_no not in self._users:
            with self.db.connection() as conn:
                row = conn.execute(
                    "select id, student_no, name, is_admin from tf_students where student_no = %s",
                    (student_no,),
                ).fetchone()
            self._users[student_no] = self.service.User(*row)
        return self._users[student_no]

    def apply(self, student_no, team_no):
        return self.service.apply(self.user(student_no), team_no)

    def vote(self, voter_no, applicant_no, yes):
        return self.service.vote(self.user(voter_no), applicant_no, yes)

    def close(self):
        raise NotImplementedError("모집 마감은 4단계에서 만듦")

    def assign_and_confirm(self):
        raise NotImplementedError("배정은 4단계에서 만듦")

    def unassigned(self):
        return self.service.unassigned()

    def teams(self):
        with self.db.connection() as conn:
            (no,) = conn.execute(
                "select student_no from tf_students where not is_admin order by id limit 1"
            ).fetchone()
        return self.service.snapshot(self.user(no)).teams

    def _latest(self, student_no, column):
        with self.db.connection() as conn:
            row = conn.execute(
                f"select a.{column} from tf_applications a join tf_students s on s.id = a.student_id "
                "where s.student_no = %s order by a.id desc limit 1",
                (student_no,),
            ).fetchone()
        return row[0] if row else None

    def application_status(self, student_no):
        return self._latest(student_no, "status")

    def application_reason(self, student_no):
        return self._latest(student_no, "reason") or ""
