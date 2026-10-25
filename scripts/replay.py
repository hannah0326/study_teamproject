# 작성: 2026-10-26 00:20 KST
"""부록 시나리오를 메모리 엔진으로 재생해 단계별 기대/실제를 표로 보여 준다.

사용: python scripts/replay.py [쉬움|중간|어려움]   (인자가 없으면 3개 모두)
어긋난 단계가 하나라도 있으면 종료 코드 1.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from teamapp.engine import Engine  # noqa: E402
from teamapp.roster import parse_roster  # noqa: E402
from tests.fixtures.runners import EngineRunner  # noqa: E402
from tests.fixtures.scenarios import SCENARIOS, play  # noqa: E402


def main(names: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    failed = 0
    for name in names or list(SCENARIOS):
        sc = SCENARIOS[name]
        students = parse_roster((ROOT / "tests" / "fixtures" / f"{sc.csv_name}.csv").read_bytes())
        runner = EngineRunner(Engine(students, sc.team_count))
        print(f"\n=== {name} (팀 {sc.team_count}개, 학생 {len(students)}명) ===")
        print(f"{'단계':<3} {'일치':<3} {'기대':<18} {'실제':<18} 하는 일")
        for r in play(sc, runner):
            mark = "✓" if r.ok else "✗"
            print(
                f"{r.no:<4} {mark:<3} {'/'.join(r.expected):<18} {'/'.join(r.actual):<18} {r.label}"
                + (f"  [{r.note}]" if r.note else "")
            )
            failed += 0 if r.ok else 1
        print("최종 팀 구성:")
        for n, members in runner.teams().items():
            print(f"  팀{n}: " + ", ".join(m.name for m in members))
    print("\n" + ("모든 단계 일치" if not failed else f"어긋난 단계 {failed}개"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
