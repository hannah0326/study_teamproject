# 작성: 2026-10-25 23:25 KST
"""로그인 화면과 로그인한 사람 표시(whoami)."""
import streamlit as st

from teamapp import service, ui_common
from teamapp.service import User


def render() -> User | None:
    user = st.session_state.get("user")
    if user is not None:
        with st.container(key="whoami"):
            st.write(user.name + (" (관리자)" if user.is_admin else ""))
            if st.button("로그아웃", key="logout"):
                del st.session_state["user"]
                ui_common.clear_result()
                st.rerun()
        return user

    st.title("팀 편성")
    st.text_input("학번", key="login_student_no")
    st.text_input("비밀번호", type="password", key="login_password")
    if st.button("로그인", key="login_submit"):
        try:
            found = service.login(
                st.session_state.get("login_student_no", ""),
                st.session_state.get("login_password", ""),
            )
        except Exception as e:  # noqa: BLE001 - 오류 내용은 화면에 쓰지 않음
            print(f"로그인 중 오류: {type(e).__name__}")
            ui_common.set_result("막힘", "처리 중 오류가 발생함. 잠시 뒤 다시 시도하세요")
            return None
        if found is None:
            ui_common.set_result("막힘", "학번이나 비밀번호가 맞지 않음")
            return None
        st.session_state["user"] = found
        ui_common.set_result("승인", "로그인함")
        st.rerun()
    return None
