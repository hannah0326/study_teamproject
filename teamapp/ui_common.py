# 작성: 2026-10-25 23:25 KST
"""화면 공통: 결과 안내(result)와 오류를 일반 문구로 바꾸는 실행 도우미."""
from typing import Callable

import streamlit as st

from teamapp.rules import Decision

_STATE_KEY = "last_result"
EMPTY_TEXT = "결과 안내가 여기에 나옴"


def set_result(word: str, message: str = "") -> None:
    """결과 안내는 승인, 대기, 거절, 막힘 가운데 하나로 시작한다. 다음 동작까지 유지된다."""
    st.session_state[_STATE_KEY] = f"{word}: {message}" if message else word


def clear_result() -> None:
    st.session_state.pop(_STATE_KEY, None)


def render_result() -> None:
    with st.container(key="result"):
        st.write(st.session_state.get(_STATE_KEY, EMPTY_TEXT))


def run_action(action: Callable[[], Decision]) -> Decision | None:
    """서비스 호출을 실행해 결과 안내에 반영한다. 예기치 못한 오류의 내용은 화면에 쓰지 않는다."""
    try:
        decision = action()
    except PermissionError:
        set_result("막힘", "관리자만 쓸 수 있는 기능임")
        return None
    except Exception as e:  # noqa: BLE001 - 오류 문구에 접속 정보가 섞일 수 있어 종류만 남김
        print(f"처리 중 오류: {type(e).__name__}")
        set_result("막힘", "처리 중 오류가 발생함. 잠시 뒤 다시 시도하세요")
        return None
    set_result(decision.word, decision.reason)
    return decision
