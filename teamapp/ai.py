# 작성: 2026-10-26 03:21 KST
"""오픈라우터 호출과 배정안 해석. 키는 요청 헤더에만 쓰고 결과나 오류에 넣지 않는다."""
import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

import requests

from teamapp import config
from teamapp.rules import Student

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_TOKENS = 8000
DETAIL_LIMIT = 300  # 실패 이유로 남기는 글자 수
_KEY_LIKE = re.compile(r"sk-or-[\w-]+")


@dataclass(frozen=True)
class AiResult:
    ok: bool
    text: str | None
    error: str | None  # timeout, empty, http_<코드>, bad_response, network, no_key
    seconds: float
    detail: str | None = None  # 실패 이유(오픈라우터 오류 문구 등). 키는 가려서 짧게


def clean(text: str | None, limit: int = DETAIL_LIMIT) -> str | None:
    """기록용 글: 키처럼 생긴 문자열을 가리고, 공백을 하나로 줄이고, limit 글자로 자른다."""
    if text is None:
        return None
    key = config.get_secret("OPENROUTER_API_KEY")
    if key:
        text = text.replace(key, "***")
    text = " ".join(_KEY_LIKE.sub("***", str(text)).split())
    return text[:limit]


def _error_reason(data) -> str | None:
    """오픈라우터 오류 본문에서 이유를 꺼낸다. 위쪽 제공자의 원래 문구(metadata.raw)가 있으면 함께."""
    err = data.get("error") if isinstance(data, dict) else None
    if not isinstance(err, dict):
        return None
    parts = [str(err.get("message") or "")]
    raw = (err.get("metadata") or {}).get("raw") if isinstance(err.get("metadata"), dict) else None
    if raw:
        parts.append(str(raw))
    return clean(" / ".join(p for p in parts if p))


class AssignParseError(ValueError):
    """AI의 답을 배정안으로 읽을 수 없음."""


def call_model(
    model: str,
    messages: list[dict],
    *,
    timeout: float = config.AI_TIMEOUT_SECONDS,
    http_post: Callable = requests.post,
) -> AiResult:
    """모델 하나를 부른다. 시작부터 응답을 다 받을 때까지 전체 timeout 초를 재서 넘으면 끊는다.

    요청 함수의 timeout 은 응답이 시작될 때까지만 재는 경우가 많아, 요청은 별도 스레드에서 하고
    이쪽에서 전체 시간을 기다린다. 끊긴 스레드는 데몬이라 앱을 붙잡지 않는다.
    """
    key = config.get_secret("OPENROUTER_API_KEY")
    if not key:
        return AiResult(False, None, "no_key", 0.0)
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "reasoning": {"effort": "low"},
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    box: dict[str, AiResult] = {}
    start = time.monotonic()

    def work() -> None:
        box["result"] = _request(http_post, body, headers, timeout, start)

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    worker.join(timeout)
    if "result" not in box:
        return AiResult(False, None, "timeout", time.monotonic() - start)
    return box["result"]


def _request(http_post: Callable, body: dict, headers: dict, timeout: float, start: float) -> AiResult:
    def done(ok: bool, text: str | None, error: str | None, detail: str | None = None) -> AiResult:
        return AiResult(ok, text, error, time.monotonic() - start, detail)

    try:
        resp = http_post(OPENROUTER_URL, json=body, headers=headers, timeout=(10, timeout))
    except Exception:  # noqa: BLE001 - 예외 문구에 헤더(키)가 섞일 수 있어 종류 코드만 남김
        return done(False, None, "network")
    if resp.status_code != 200:
        try:
            reason = _error_reason(resp.json())
        except Exception:  # noqa: BLE001 - 오류 본문을 못 읽어도 코드는 남김
            reason = None
        return done(False, None, f"http_{resp.status_code}", reason)
    try:
        data = resp.json()
        if "error" in data and "choices" not in data:
            code = (data.get("error") or {}).get("code")
            error = f"http_{code}" if isinstance(code, int) else "bad_response"
            return done(False, None, error, _error_reason(data))
        choice = data["choices"][0]
        content = choice["message"].get("content")
    except Exception:  # noqa: BLE001 - 응답 구조가 다르면 모두 같은 실패로 봄
        return done(False, None, "bad_response", "응답에 choices[0].message 가 없음")
    if not content or not str(content).strip():
        return done(False, None, "empty", f"finish_reason={choice.get('finish_reason')}")
    return done(True, str(content), None)


def _describe(s: Student) -> dict:
    return {"student_no": s.student_no, "name": s.name, "main_role": s.main_role,
            "sub_roles": list(s.sub_roles)}


def build_messages(teams: Mapping[int, Sequence[Student]], free: Sequence[Student]) -> list[dict]:
    """지금 팀 구성, 팀이 없는 학생과 역할, 규칙, 응답 형식을 담은 요청 메시지."""
    state = {
        "teams": {str(n): [_describe(s) for s in m] for n, m in sorted(teams.items())},
        "students_without_team": [_describe(s) for s in free],
    }
    rules_text = (
        "규칙:\n"
        "1. 팀이 없는 학생을 빠짐없이 한 명씩 정확히 한 팀에 넣는다.\n"
        "2. 이미 팀에 있는 학생은 옮기지 않는다. 팀원 목록에 이미 있는 학생은 답에 쓰지 않는다.\n"
        "3. 넣은 뒤 모든 팀의 인원은 2~4명이어야 한다.\n"
        "4. 한 팀 안에 주 역할(main_role)이 같은 학생이 2명 이상이면 안 된다.\n"
        "5. 모든 팀에는 기획자를 맡을 학생과 웹 프로그래머를 맡을 학생이 서로 다른 사람으로 1명씩 있어야 한다. "
        "주 역할이나 보조 역할(sub_roles)로 맡을 수 있다.\n"
    )
    answer_format = (
        '답은 JSON 하나로만 한다. 형식: {"teams": {"팀 번호": ["새로 넣는 학생의 학번", ...]}}\n'
        '예: {"teams": {"1": ["2026310"], "2": ["2026306", "2026313"]}}\n'
        "설명이나 다른 글은 쓰지 않는다."
    )
    return [
        {"role": "system", "content": "너는 팀 편성 규칙을 정확히 지키는 배정 도우미다. " + answer_format},
        {"role": "user", "content": rules_text + "\n지금 상태:\n"
            + json.dumps(state, ensure_ascii=False, indent=1) + "\n\n" + answer_format},
    ]


def _json_text(text: str) -> str:
    """코드 블록이나 앞뒤 설명이 붙어 있어도 JSON 객체 부분만 꺼낸다."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        return fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise AssignParseError("JSON 객체가 없음")
    return text[start : end + 1]


def parse_assignment(
    text: str, teams: Mapping[int, Sequence[Student]], free: Sequence[Student]
) -> dict[int, list[Student]]:
    """AI의 답을 {팀 번호: 새로 넣는 학생 목록} 으로 읽는다. 규칙 검사는 rules.validate_assignment 가 한다."""
    try:
        data = json.loads(_json_text(text or ""))
    except json.JSONDecodeError as e:
        raise AssignParseError("JSON 을 읽을 수 없음") from e
    raw = data.get("teams") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        raise AssignParseError('"teams" 가 없음')
    by_no = {s.student_no: s for s in free}
    members = {s.student_no for m in teams.values() for s in m}
    result: dict[int, list[Student]] = {n: [] for n in teams}
    for key, nos in raw.items():
        try:
            team_no = int(str(key).removeprefix("팀"))
        except ValueError as e:
            raise AssignParseError(f"팀 번호를 읽을 수 없음: {key}") from e
        if team_no not in teams:
            raise AssignParseError(f"없는 팀: {team_no}")
        if not isinstance(nos, list):
            raise AssignParseError(f"팀{team_no} 의 값이 목록이 아님")
        for no in map(str, nos):
            if no in members:
                raise AssignParseError(f"이미 팀이 있는 학생을 옮김: {no}")
            if no not in by_no:
                raise AssignParseError(f"없는 학생: {no}")
            result[team_no].append(by_no[no])
    return result
