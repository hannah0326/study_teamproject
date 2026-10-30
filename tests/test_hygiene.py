# 작성: 2026-10-31 05:06 KST
"""제출 전 보안과 정직성 점검. 저장소에 올라갈 파일을 대상으로 하며, 비밀 값은 출력하지 않고 일치 여부만 본다."""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_FILES = [ROOT / "streamlit_app.py", *sorted((ROOT / "teamapp").glob("*.py"))]
PLACEHOLDER_PASSWORDS = {b"SECRETPW"}  # 시험에서 일부러 쓰는 가짜 비밀번호


def repo_files() -> list[Path]:
    """커밋되었거나 커밋될 수 있는 파일(무시 목록에 든 파일은 뺌)."""
    out = subprocess.run(
        ["git", "-c", "core.quotepath=false", "ls-files", "-co", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout
    return [ROOT / f for f in out.splitlines() if f and (ROOT / f).is_file()]


def env_values() -> list[bytes]:
    env = ROOT / ".env"
    if not env.exists():
        return []
    values = []
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if len(value) >= 6:
                values.append(value.encode())
    return values


def test_env_ignored():
    assert subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT).returncode == 0
    assert ROOT / ".env" not in repo_files()


def test_no_secrets_in_tracked_files():
    values = env_values()
    key_like = re.compile(rb"sk-or-v1-[A-Za-z0-9]{20,}")
    db_url = re.compile(rb"postgres(?:ql)?://[^\s:/@]+:([^\s@]+)@")
    found = []
    for path in repo_files():
        data = path.read_bytes()
        if any(v in data for v in values):
            found.append(f"{path.name}: .env 의 실제 값")
        if key_like.search(data):
            found.append(f"{path.name}: 오픈라우터 키 모양")
        for m in db_url.finditer(data):
            if m.group(1) not in PLACEHOLDER_PASSWORDS:
                found.append(f"{path.name}: 비밀번호가 든 DB 주소")
    assert found == []  # 값 자체는 출력하지 않고 파일 이름과 종류만


def test_no_openrouter_free_router():
    from teamapp import config

    assert "openrouter/free" not in config.MODELS
    assert all("openrouter/free" not in p.read_text(encoding="utf-8") for p in APP_FILES)


def test_all_tables_prefixed_tf():
    sql = (ROOT / "schema.sql").read_text(encoding="utf-8")
    names = re.findall(r"create table if not exists (\w+)", sql)
    assert names and all(n.startswith("tf_") for n in names)
    assert all(n.startswith("tf_") for n in re.findall(r"alter table (\w+)", sql))


def test_no_scenario_names_in_app_code():
    """연습용 시나리오의 학생 이름이나 학번에 맞춘 코드가 없음(이름이 아니라 CSV 의 역할 열로만 판정)."""
    pattern = re.compile(r"학생\d|2026[1-3]\d\d")
    hits = [p.name for p in APP_FILES if pattern.search(p.read_text(encoding="utf-8"))]
    assert hits == []


def _prd_keys() -> list[str]:
    prd = (ROOT / "docs" / "PRD.md").read_text(encoding="utf-8")
    section = prd.split("### 5.2", 1)[1].split("###", 1)[0]
    keys = []
    for row in section.splitlines():
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[2].startswith("`"):
            keys += re.findall(r"`([^`]+)`", cells[2])
    return keys


def test_keys_table_present():
    """PRD 5.2절 표의 key 가 코드에 그대로 있음(번호·학번이 붙는 key 는 앞부분으로 확인)."""
    code = "\n".join(p.read_text(encoding="utf-8") for p in APP_FILES)
    keys = _prd_keys()
    assert len(keys) >= 17
    missing = []
    for k in keys:
        if re.fullmatch(r"[a-z_]+_\d+", k):  # team_1, apply_1 …
            prefix = k.rsplit("_", 1)[0] + "_"
            ok = f'key=f"{prefix}{{' in code
        elif "{" in k:  # vote_yes_{지원자 학번}
            ok = f'key=f"{k.split("{")[0]}{{' in code
        else:
            ok = f'key="{k}"' in code
        if not ok:
            missing.append(k)
    assert missing == []
    assert 'key="refresh"' not in code  # 자동 갱신을 골라 새로 고침 단추는 두지 않음


@pytest.mark.db
def test_rls_enabled_on_all_tf_tables(db):
    """Supabase 공개 API로 표(비밀번호 해시 포함)를 읽지 못하게 모든 tf_ 표에 RLS 를 켬."""
    with db.connection() as conn:
        rows = conn.execute(
            "select c.relname, c.relrowsecurity from pg_class c "
            "join pg_namespace n on n.oid = c.relnamespace "
            "where n.nspname = 'public' and c.relkind = 'r' and c.relname like 'tf\\_%'"
        ).fetchall()
    assert len(rows) == 8
    assert [name for name, on in rows if not on] == []
