# 작성: 2026-10-26 03:22 KST
"""AI 배정 흐름: 가능 여부 확인 → 1차 → 2차 → 3차 모델 → 앱이 직접 배정."""
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Mapping, Sequence

from teamapp import ai, config, rules, solver
from teamapp.ai import AiResult, AssignParseError
from teamapp.rules import Student

NO_ASSIGNMENT = "규칙을 지키는 배정이 없음"
SOLVER_MESSAGE = "3차 모델까지 실패하여 앱이 직접 배정함"

_EXPLAIN = {
    "timeout": "제한 시간 안에 응답하지 않음",
    "empty": "빈 응답",
    "http_404": "모델을 찾을 수 없음(404)",
    "http_429": "사용량이 많다며 거절함(429)",
    "bad_response": "응답 구조가 다름",
    "network": "연결 오류",
    "no_key": "키가 설정되지 않음",
    "parse_error": "배정안을 읽을 수 없음",
    "rule_violation": "배정안이 규칙 검사를 통과하지 못함",
}


@dataclass(frozen=True)
class AttemptLog:
    step: int
    model: str
    result: str  # ok 또는 실패 종류
    seconds: float
    detail: str | None = None  # 실패 이유(오류 문구, 해석 실패 이유와 답의 앞부분 등)
    started_at: datetime | None = None  # 이 모델을 부르기 시작한 때(UTC)


@dataclass(frozen=True)
class FlowResult:
    assignment: dict[int, list[Student]] | None
    source: str  # ai1, ai2, ai3, solver, none
    message: str
    log: list[AttemptLog] = field(default_factory=list)


def explain(result: str) -> str:
    return _EXPLAIN.get(result, result)


def describe_attempt(a: AttemptLog) -> str:
    """기록 한 줄: 몇 차 모델이 어떻게 끝났는지와 실패 이유."""
    # 모델 이름 바로 뒤에 쌍점을 두지 않는다: '…:free: …' 는 화면에서 이모지 약속어로 바뀜
    line = f"{a.step}차 모델({a.model}) — {'성공' if a.result == 'ok' else explain(a.result)} ({a.seconds}초)"
    return f"{line} — {a.detail}" if a.detail else line


def run(
    teams: Mapping[int, Sequence[Student]],
    free: Sequence[Student],
    *,
    call: Callable[[str, list[dict]], AiResult] | None = None,
    solve: Callable = solver.solve,
    on_status: Callable[[str], None] = lambda s: None,
    models: Sequence[str] = config.MODELS,
    limit: float = config.AI_TIMEOUT_SECONDS + 5,
    tick: float = 1.0,
) -> FlowResult:
    """배정안을 만든다. on_status 는 이 함수를 부른 스레드에서만 불린다(화면 갱신용)."""
    call = call or ai.call_model
    found = solve(teams, free)
    if found.assignment is None:
        message = f"{NO_ASSIGNMENT}: {found.reason}"
        on_status(message)
        return FlowResult(None, "none", message)
    if not free:
        message = "팀이 없는 학생이 없어 배정할 것이 없음"
        on_status(message)
        return FlowResult(found.assignment, "solver", message)

    messages = ai.build_messages(teams, free)
    log: list[AttemptLog] = []
    for step, model in enumerate(models, 1):
        label = f"{step}차 모델({model})"
        started_at = datetime.now(timezone.utc)
        reply = _wait(call, model, messages, label, on_status, limit, tick)
        outcome, detail = reply.error or "ok", reply.detail
        assignment = None
        if reply.ok:
            try:
                assignment = ai.parse_assignment(reply.text, teams, free)
            except AssignParseError as e:
                outcome, detail = "parse_error", _with_answer(str(e), reply.text)
            else:
                problems = rules.validate_assignment(teams, free, assignment)
                if problems:
                    outcome, detail = "rule_violation", _with_answer("; ".join(problems), reply.text)
        log.append(AttemptLog(step, model, outcome, round(reply.seconds, 1), detail, started_at))
        if outcome == "ok":
            message = f"{label}의 배정안이 5가지 검사를 통과함"
            on_status(message)
            return FlowResult(assignment, f"ai{step}", message, log)
        on_status(f"{label} 실패: {explain(outcome)}")  # 바깥에서 온 이유는 기록 줄에만 남김
    on_status(SOLVER_MESSAGE)
    return FlowResult(found.assignment, "solver", SOLVER_MESSAGE, log)


def _with_answer(reason: str, text: str | None) -> str:
    """실패 이유 뒤에 모델 답의 앞부분을 붙인다(키처럼 생긴 글은 가리고 짧게)."""
    return f"{ai.clean(reason, 150)} | 답: {ai.clean(text, 240)}"


def _wait(call, model, messages, label, on_status, limit, tick) -> AiResult:
    """호출은 다른 스레드에서 하고, 이쪽은 tick 마다 경과를 알린다. limit 를 넘으면 끊는다."""
    box: dict[str, AiResult] = {}
    start = time.monotonic()

    def work() -> None:
        try:
            box["reply"] = call(model, messages)
        except Exception:  # noqa: BLE001 - 호출 함수의 예상 밖 오류도 실패로 보고 다음 모델로
            box["reply"] = AiResult(False, None, "network", time.monotonic() - start)

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    while True:
        elapsed = time.monotonic() - start
        on_status(f"{label} 응답을 기다리는 중 … 경과 {int(elapsed)}초")
        worker.join(tick)
        if "reply" in box:
            return box["reply"]
        if time.monotonic() - start >= limit:
            return AiResult(False, None, "timeout", time.monotonic() - start)
