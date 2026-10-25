# 작성: 2026-10-25 23:22 KST
"""DB 연결. 연결 풀을 한 번만 만들어 재사용한다."""
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
import streamlit as st
from psycopg_pool import ConnectionPool

from teamapp import config

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


@st.cache_resource(show_spinner=False)
def get_pool() -> ConnectionPool:
    """풀은 프로세스에서 한 번만 만든다(크기 2~4). 꺼낼 때 확인 질의로 끊긴 연결을 걸러 낸다."""
    url = config.get_secret("DATABASE_URL")
    if not url:
        raise RuntimeError("DB 주소가 설정되지 않음")
    return ConnectionPool(
        url,
        min_size=2,
        max_size=4,
        timeout=30,
        check=ConnectionPool.check_connection,
        kwargs={"connect_timeout": 15},
        open=True,
    )


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    """풀에서 연결을 하나 빌린다. 블록이 끝나면 커밋, 오류면 롤백."""
    with get_pool().connection() as conn:
        yield conn


def apply_schema() -> None:
    with connection() as conn:
        conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
