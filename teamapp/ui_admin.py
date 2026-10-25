# 작성: 2026-10-25 23:25 KST
"""관리자 화면. 관리자 기능은 서비스에서 매번 관리자인지 다시 확인한다."""
import streamlit as st

from teamapp import service, ui_common
from teamapp.service import User


def render(user: User) -> None:
    st.subheader("명단 올리기")
    roster = st.file_uploader("명단 CSV", type=["csv"], key="admin_roster_file")
    team_count = st.number_input(
        "팀 수", min_value=1, max_value=10, value=3, step=1, key="admin_team_count"
    )
    if st.button("명단으로 처음 상태 만들기", key="admin_start"):
        if roster is None:
            ui_common.set_result("막힘", "명단 CSV 파일을 먼저 고르세요")
        else:
            data = roster.getvalue()
            ui_common.run_action(lambda: service.start_from_roster(user, data, int(team_count)))
