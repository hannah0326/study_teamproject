# 작성: 2026-10-25 23:25 KST
"""앱이 시작할 때 한 번 하는 일: 스키마 적용과 관리자 계정 만들기(또는 비밀번호 갱신)."""
import streamlit as st

from teamapp import db, service


@st.cache_resource(show_spinner=False)
def ensure_ready() -> bool:
    db.apply_schema()
    service.ensure_admin()
    return True
