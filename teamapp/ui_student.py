# 작성: 2026-10-26 00:23 KST
"""학생 화면. 팀 목록, 지원 목록, 결과 안내를 5초마다 함께 다시 그린다."""
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from teamapp import config, service, ui_common
from teamapp.rules import Student
from teamapp.service import Snapshot, User

KST = ZoneInfo("Asia/Seoul")
REFRESH_SECONDS = 5
_WAITING_KEY = "waiting_apply"  # 대기를 받은 내 지원: (학번, 팀 번호)


def render(user: User) -> None:
    _live(user)


def _do_apply(user: User, team_no: int) -> None:
    decision = ui_common.run_action(lambda: service.apply(user, team_no))
    if decision is not None and decision.word == "대기":
        st.session_state[_WAITING_KEY] = (user.student_no, team_no)
    else:
        st.session_state.pop(_WAITING_KEY, None)


def _do_vote(user: User, applicant_no: str, yes: bool) -> None:
    st.session_state.pop(_WAITING_KEY, None)
    ui_common.run_action(lambda: service.vote(user, applicant_no, yes))


@st.fragment(run_every=REFRESH_SECONDS)
def _live(user: User) -> None:
    """단추는 on_click 으로 처리한다. 콜백이 다시 그리기 전에 실행되므로 화면은 항상 동작 뒤의 상태다."""
    try:
        snap = service.snapshot(user)
    except Exception as e:  # noqa: BLE001 - 오류 문구에 접속 정보가 섞일 수 있어 종류만 남김
        ui_common.log_error("현황 조회 중 오류", e)
        st.warning("현황을 불러오지 못함. 잠시 뒤 자동으로 다시 시도함")
        ui_common.render_result()
        return
    if not snap.signed_in:  # 명단을 다시 올려 이 로그인의 계정이 없어짐
        st.session_state.pop("user", None)
        ui_common.set_result("막힘", service.REASON_RELOGIN)
        st.rerun(scope="app")

    ui_common.render_result()
    _decided_notice(user, snap)
    _my_status(snap)
    can_apply = snap.my_team is None and not _has_pending(snap) and not snap.closed
    for team_no, members in snap.teams.items():
        _team(user, snap, team_no, members, can_apply)
    _votes(user, snap)
    st.caption(f"마지막 갱신: {datetime.now(KST):%H:%M:%S} (한국 시각, {REFRESH_SECONDS}초마다 자동 갱신)")


def _has_pending(snap: Snapshot) -> bool:
    return snap.my_app is not None and snap.my_app.status == "대기"


def _describe(s: Student) -> str:
    subs = f" / 보조: {', '.join(s.sub_roles)}" if s.sub_roles else ""
    return f"{s.name} — {s.main_role}{subs}"


def _decided_notice(user: User, snap: Snapshot) -> None:
    """대기를 받은 내 지원이 다른 팀원의 표로 결정되면 알린다. result 는 동작 직후의 결과라 바꾸지 않는다."""
    app = snap.my_app
    if app is None or app.status == "대기":
        return
    if st.session_state.get(_WAITING_KEY) != (user.student_no, app.team_no):
        return
    if app.status == "승인":
        st.success(f"내 지원이 팀{app.team_no}에 승인됨")
    else:
        reason = f": {app.reason}" if app.reason else ""
        st.warning(f"내 지원이 팀{app.team_no}에서 거절됨{reason}")


def _my_status(snap: Snapshot) -> None:
    if snap.closed:
        st.info("모집이 마감됨")
    if snap.my_team is None:
        st.write("아직 팀이 없음")
    if snap.my_app is not None:
        app = snap.my_app
        reason = f" ({app.reason})" if app.reason else ""
        st.write(f"내 지원: 팀{app.team_no} — {app.status}{reason}")


def _team(user: User, snap: Snapshot, team_no: int, members: list[Student], can_apply: bool) -> None:
    with st.container(key=f"team_{team_no}", border=True):
        mine = " · 내 팀" if snap.my_team == team_no else ""
        st.markdown(f"**팀{team_no}** ({len(members)}/{config.MAX_TEAM}){mine}")
        for s in members:
            st.write(_describe(s))
        # 팀이 꽉 참, 같은 주 역할 등은 단추를 보이게 두고 누르면 막힘 이유를 보인다
        if can_apply:
            st.button(
                f"팀{team_no}에 지원", key=f"apply_{team_no}",
                on_click=_do_apply, args=(user, team_no),
            )


def _votes(user: User, snap: Snapshot) -> None:
    mine = [p for p in snap.pending if p.team_no == snap.my_team]
    if not mine:
        return
    st.markdown("**내 팀에 온 지원**")
    size = len(snap.teams.get(snap.my_team, []))
    for p in mine:
        no = p.applicant.student_no
        yes = sum(p.votes.values())
        st.write(f"{_describe(p.applicant)} · 찬성 {yes}/{size}")
        if no in snap.my_votes:
            st.write(f"내 투표: {'찬성' if snap.my_votes[no] else '거부'}")
            continue
        left, right = st.columns(2)
        left.button("찬성", key=f"vote_yes_{no}", on_click=_do_vote, args=(user, no, True))
        right.button("거부", key=f"vote_no_{no}", on_click=_do_vote, args=(user, no, False))
