# 작성: 2026-10-25 23:25 KST
"""관리자 화면. 관리자 기능은 서비스에서 매번 관리자인지 다시 확인한다."""
from typing import Callable

import streamlit as st

from teamapp import config, service, ui_common
from teamapp.rules import Decision
from teamapp.service import AdminView, User


def render(user: User) -> None:
    _roster(user)
    st.subheader("모집 마감과 배정")
    left, middle, right = st.columns(3)
    left.button("모집 마감", key="admin_close", on_click=_act, args=(lambda: service.close_recruitment(user),))
    assign_clicked = middle.button("AI 배정", key="admin_assign")
    right.button("배정안 확정", key="admin_confirm", on_click=_act,
                 args=(lambda: service.confirm_assignment(user),))

    with st.container(key="assign_status", border=True):
        live = st.empty()
        if assign_clicked:  # 오래 걸리므로 화면을 그리는 중에 실행해 진행 안내를 갱신한다
            ui_common.run_action(lambda: service.propose_assignment(user, lambda s: live.info(s)))
            live.empty()
        view = _load(user)
        if view is not None:
            _assign_status(view)
    if view is not None:
        _teams(view)


def _act(action: Callable[[], Decision]) -> None:
    ui_common.run_action(action)


def _load(user: User) -> AdminView | None:
    try:
        return service.admin_view(user)
    except Exception as e:  # noqa: BLE001 - 오류 문구에 접속 정보가 섞일 수 있어 종류만 남김
        ui_common.log_error("관리자 현황 조회 중 오류", e)
        st.warning("현황을 불러오지 못함. 잠시 뒤 다시 시도하세요")
        return None


def _roster(user: User) -> None:
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


def _assign_status(view: AdminView) -> None:
    """AI 배정 안내: 마지막 결과(실패·배정 없음 이유 포함)와 검사를 통과한 배정안."""
    if view.status:
        first, *attempts = view.status.splitlines()
        st.write(first)
        for line in attempts:  # 오픈라우터 문구와 모델 답이 섞이므로 마크다운으로 해석하지 않음
            st.text(line)
    elif not view.closed:
        st.caption("모집을 마감한 뒤 AI 배정을 누르세요")
    if view.proposal is not None:
        st.markdown("**배정안**" + (" (확정함)" if view.confirmed else ""))
        for team_no, added in sorted(view.proposal.teams.items()):
            for s in added:
                st.write(f"팀{team_no} ← {ui_common.describe(s)}")


def _teams(view: AdminView) -> None:
    state = "확정함" if view.confirmed else ("모집 마감" if view.closed else "모집 중")
    st.subheader(f"팀 현황 ({state})")
    for team_no, members in view.teams.items():
        with st.container(key=f"team_{team_no}", border=True):
            st.markdown(f"**팀{team_no}** ({len(members)}/{config.MAX_TEAM})")
            for s in members:
                st.write(ui_common.describe(s))
    with st.container(key="unassigned", border=True):
        st.markdown("**팀이 없는 학생**")
        if view.free:
            for s in view.free:
                st.write(ui_common.describe(s))
        else:
            st.write("팀이 없는 학생이 없음")
