# 작성: 2026-10-26 03:21 KST
"""오픈라우터 호출과 응답 해석. 실제로 부르지 않고 가짜 http_post 로만 시험한다."""
import json
import time

import pytest

from teamapp import ai
from teamapp.rules import Student

FAKE_KEY = "sk-or-v1-FAKEKEY0123456789"


def stu(no: str, main: str, subs: tuple[str, ...] = ()) -> Student:
    return Student(no, f"학생{no[-2:]}", main, subs)


TEAMS = {1: [stu("2026301", "기획자"), stu("2026304", "웹 프로그래머")], 2: [stu("2026302", "기획자")]}
FREE = [stu("2026306", "웹 프로그래머"), stu("2026310", "테스터")]


class FakeResp:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def chat(content):
    return {"choices": [{"message": {"content": content}}]}


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)


def post_returning(resp, seen=None):
    def http_post(url, **kwargs):
        if seen is not None:
            seen.append((url, kwargs))
        return resp

    return http_post


def test_call_ok_and_request_shape():
    seen = []
    r = ai.call_model("m/one:free", [{"role": "user", "content": "x"}],
                      http_post=post_returning(FakeResp(200, chat('{"teams": {}}')), seen))
    assert r.ok and r.text == '{"teams": {}}' and r.error is None
    url, kwargs = seen[0]
    assert url == ai.OPENROUTER_URL
    body = kwargs["json"]
    assert body["model"] == "m/one:free"
    assert body["reasoning"] == {"effort": "low"}
    assert body["max_tokens"] == 8000
    assert body["response_format"] == {"type": "json_object"}
    assert kwargs["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"


@pytest.mark.parametrize("content", ["", "   ", None])
def test_call_empty_content_is_empty(content):
    r = ai.call_model("m", [], http_post=post_returning(FakeResp(200, chat(content))))
    assert not r.ok and r.error == "empty"


@pytest.mark.parametrize("code, error", [(404, "http_404"), (429, "http_429"), (502, "http_502")])
def test_call_http_errors(code, error):
    r = ai.call_model("m", [], http_post=post_returning(FakeResp(code, {"error": {"message": "x"}})))
    assert not r.ok and r.error == error


def test_call_bad_body_is_bad_response():
    r = ai.call_model("m", [], http_post=post_returning(FakeResp(200, ValueError("not json"))))
    assert not r.ok and r.error == "bad_response"
    r = ai.call_model("m", [], http_post=post_returning(FakeResp(200, {"choices": []})))
    assert not r.ok and r.error == "bad_response"


def test_call_overall_timeout():
    """요청 함수의 timeout 값에 기대지 않고, 시작부터 응답까지 전체 시간을 재서 끊는다."""
    def slow_post(url, **kwargs):
        time.sleep(3)  # 응답이 천천히 옴
        return FakeResp(200, chat("{}"))

    start = time.monotonic()
    r = ai.call_model("m", [], timeout=0.5, http_post=slow_post)
    elapsed = time.monotonic() - start
    assert not r.ok and r.error == "timeout"
    assert 0.4 <= elapsed < 1.5
    assert 0.4 <= r.seconds < 1.5


def test_error_text_never_contains_key():
    def leaky_post(url, **kwargs):
        raise RuntimeError(f"connection failed, headers={kwargs['headers']}")

    r = ai.call_model("m", [], http_post=leaky_post)
    assert not r.ok and r.error == "network"
    assert FAKE_KEY not in repr(r)


def test_http_error_keeps_short_reason():
    body = {"error": {"message": "Rate limit exceeded: free-models-per-day", "code": 429}}
    r = ai.call_model("m", [], http_post=post_returning(FakeResp(429, body)))
    assert r.error == "http_429" and "free-models-per-day" in r.detail


def test_upstream_raw_reason_is_kept():
    body = {"error": {"message": "Provider returned error", "code": 429,
                      "metadata": {"raw": "google/gemma is temporarily rate-limited upstream"}}}
    r = ai.call_model("m", [], http_post=post_returning(FakeResp(429, body)))
    assert "Provider returned error" in r.detail and "rate-limited upstream" in r.detail


def test_empty_keeps_finish_reason():
    body = {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
    r = ai.call_model("m", [], http_post=post_returning(FakeResp(200, body)))
    assert r.error == "empty" and "finish_reason=length" in r.detail


def test_detail_is_short_and_never_contains_key():
    body = {"error": {"message": f"bad key {FAKE_KEY} " + "x" * 1000, "code": 401}}
    r = ai.call_model("m", [], http_post=post_returning(FakeResp(401, body)))
    assert r.error == "http_401"
    assert FAKE_KEY not in r.detail and "sk-or-" not in r.detail
    assert len(r.detail) <= ai.DETAIL_LIMIT


def test_clean_hides_any_key_like_text():
    assert ai.clean("token sk-or-v1-abcDEF123_xyz end") == "token *** end"
    assert ai.clean("  여러   줄\n\n 공백  ") == "여러 줄 공백"
    assert ai.clean(None) is None


def test_no_key_does_not_call(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.setattr(ai.config, "get_secret", lambda name: None)
    called = []
    r = ai.call_model("m", [], http_post=post_returning(FakeResp(200, chat("{}")), called))
    assert not r.ok and r.error == "no_key" and called == []


def test_build_messages_mentions_state_and_format():
    msgs = ai.build_messages(TEAMS, FREE)
    assert msgs[0]["role"] == "system" and msgs[-1]["role"] == "user"
    text = "\n".join(m["content"] for m in msgs)
    for no in ("2026301", "2026304", "2026302", "2026306", "2026310"):
        assert no in text
    assert '"teams"' in text and "2~4" in text and "옮기지" in text


def test_parse_plain_json():
    got = ai.parse_assignment('{"teams": {"2": ["2026306", "2026310"]}}', TEAMS, FREE)
    assert got == {1: [], 2: [FREE[0], FREE[1]]}


def test_parse_code_fenced_json():
    text = "배정안입니다.\n```json\n" + json.dumps({"teams": {"1": ["2026310"], "2": [2026306]}}) + "\n```"
    got = ai.parse_assignment(text, TEAMS, FREE)
    assert got == {1: [FREE[1]], 2: [FREE[0]]}


@pytest.mark.parametrize(
    "text",
    [
        '{"teams": {"2": ["2026399"]}}',  # 없는 학생
        '{"teams": {"9": ["2026306"]}}',  # 없는 팀
        '{"teams": {"2": ["2026301"]}}',  # 이미 팀이 있는 학생을 옮김
        "배정할 수 없습니다",  # JSON 아님
        '{"assignment": {}}',  # 형식이 다름
        '{"teams": {"2": "2026306"}}',  # 목록이 아님
    ],
    ids=["없는 학생", "없는 팀", "기존 팀원 옮김", "JSON 아님", "teams 없음", "목록 아님"],
)
def test_parse_rejects_bad_answers(text):
    with pytest.raises(ai.AssignParseError):
        ai.parse_assignment(text, TEAMS, FREE)
