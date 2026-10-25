# 작성: 2026-10-25 23:25 KST
"""필요한 설정 값이 있는지만 출력한다(값은 출력하지 않음). 하나라도 없으면 종료 코드 1."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from teamapp import config  # noqa: E402

NAMES = ("OPENROUTER_API_KEY", "DATABASE_URL", "ADMIN_PASSWORD")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    missing = 0
    for name in NAMES:
        found = bool(config.get_secret(name))
        print(f"{name}: {'있음' if found else '없음'}")
        missing += 0 if found else 1
    sys.exit(1 if missing else 0)
