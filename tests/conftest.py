# 작성: 2026-10-25 23:22 KST
import os

import pytest


def pytest_collection_modifyitems(config, items):
    """DB 시험은 RUN_DB_TESTS=1 일 때만 실행한다(개발용 DB 상태를 지우므로)."""
    if os.environ.get("RUN_DB_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="RUN_DB_TESTS=1 일 때만 실행")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def db():
    """스키마를 적용하고 모든 tf_ 테이블을 비운 DB 모듈을 돌려준다."""
    from teamapp import db as dbm

    dbm.apply_schema()
    with dbm.connection() as conn:
        conn.execute(
            "truncate tf_ai_logs, tf_settings, tf_votes, tf_applications, tf_members, "
            "tf_teams, tf_student_sub_roles, tf_students restart identity cascade"
        )
    return dbm
