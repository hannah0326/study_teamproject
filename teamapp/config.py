# 작성: 2026-10-25 23:10 KST
"""설정과 상수. 모델 이름은 이 파일에만 둔다."""
import os

from dotenv import load_dotenv

ROLES = (
    "기획자",
    "웹 프로그래머",
    "프론트엔드 디자이너",
    "테스터",
    "보고서 작성자",
    "발표자",
)
PL = "기획자"
WP = "웹 프로그래머"

MIN_TEAM = 2
MAX_TEAM = 4

# 1차, 2차, 3차 모델. 4단계 실제 호출 시험 결과로 정함(근거는 docs/근거기록.md 의 AI 호출 실패 절)
MODELS = (
    "nvidia/nemotron-3.5-super-vl:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-26b-a4b-it:free",
)
AI_TIMEOUT_SECONDS = 120

load_dotenv()


def get_secret(name: str) -> str | None:
    """환경 변수(.env 포함) → Streamlit Secrets 순으로 읽는다. 없으면 None."""
    value = os.environ.get(name)
    if value:
        return value
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:
        return None
    return str(value) if value else None
