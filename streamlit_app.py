# 작성: 2026-10-25 23:25 KST
"""진입점. 배포의 Main file path 는 이 파일 이름임."""
import streamlit as st

from teamapp import boot, ui_admin, ui_common, ui_login, ui_student

st.set_page_config(page_title="팀 편성", page_icon="👥")

try:
    boot.ensure_ready()
except Exception as e:  # noqa: BLE001 - 접속 정보가 섞일 수 있어 오류 내용은 화면에 쓰지 않음
    print(f"시작 중 오류: {type(e).__name__}")
    st.error("앱을 시작하지 못함. 설정(DB 주소, 관리자 비밀번호)을 확인하세요.")
    st.stop()

user = ui_login.render()
if user is not None and not user.is_admin:
    ui_student.render(user)  # 학생 화면은 result 를 자동 갱신 영역 안에서 그린다
else:
    if user is not None:
        ui_admin.render(user)
    ui_common.render_result()
