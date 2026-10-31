"""Kod tapşırıqları və onların testləri (gün 19).

Tapşırıq JSON-dur (`exercises/*.json`): şərt, funksiyanın adı və testlər
(`call` → `expected`, ikisi də Python ifadəsidir). Testlər Docker-də, tələbənin
`solution.py`-si yanında işləyir; hər test ayrıca `try` içindədir ki, birinin
xətası qalanlarını gizlətməsin. Nəticə JSON kimi stdout-a yazılır.

BAL YALNIZ TESTLƏRDƏNDİR: AI agentləri izah yazır, qiymət vermir.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from code_checker.sandbox import RunResult, run_python

EXERCISES_DIR = Path(__file__).parent / "exercises"


class CheckCase(BaseModel):
    name: str
    call: str
    expected: str


class Exercise(BaseModel):
    id: str
    title: str
    lesson: str = ""
    prompt: str
    function: str
    tests: list[CheckCase] = Field(min_length=1)


def load_exercise(exercise_id: str) -> Exercise:
    path = EXERCISES_DIR / f"{exercise_id}.json"
    if not path.is_file() or path.parent != EXERCISES_DIR:
        raise KeyError(f"Tapşırıq tapılmadı: {exercise_id}")
    return Exercise.model_validate_json(path.read_text(encoding="utf-8"))


def list_exercises() -> list[Exercise]:
    return [Exercise.model_validate_json(p.read_text(encoding="utf-8")) for p in sorted(EXERCISES_DIR.glob("*.json"))]


# Qiymətləndirici (grader) və tələbə kodu AYRI proseslərdədir. Eyni prosesdə olsaydı,
# tələbə kodu nəticə sətrini özü çap edib `os._exit(0)` ilə çıxa bilərdi (saxta 5/5).
# İndi: grader testləri stdin-dən oxuyur (faylda yoxdur - tələbə kodu oxuya bilməz),
# hər test üçün ayrıca uşaq proses başladır və yalnız onun QAYTARDIĞI dəyəri alır;
# öz nəticəsini öz stdout-una yazır, uşağın çıxışı ora qarışmır.
_CHILD = """import sys
sys.path.insert(0, "/work")
import solution
got = eval(sys.argv[1], {sys.argv[2]: getattr(solution, sys.argv[2])})
print("\\n@@GOT@@" + repr(got))
"""

GRADER = '''import ast, json, subprocess, sys
spec = json.loads(sys.stdin.read())
child, function, per_test = spec["child"], spec["function"], spec["per_test"]
results, printed = [], []
for case in spec["tests"]:
    row = {"name": case["name"], "ok": False, "expected": case["expected"]}
    try:
        proc = subprocess.run([sys.executable, "-I", "-c", child, case["call"], function],
                              capture_output=True, text=True, timeout=per_test)
    except subprocess.TimeoutExpired:
        row["error"] = "vaxt həddi aşıldı"
        results.append(row)
        continue
    out, marker, got = proc.stdout.rpartition("\\n@@GOT@@")
    printed.append(out[-300:])
    if proc.returncode in (-9, 137):
        row["error"] = "yaddaş həddi aşıldı (proses öldürüldü)"
    elif not marker or proc.returncode != 0:
        lines = (proc.stderr.strip() or "nəticə yoxdur").splitlines()
        row["error"] = lines[-1][:300]
    else:
        got = got.strip()
        row["got"] = got[:200]
        try:
            row["ok"] = ast.literal_eval(got) == ast.literal_eval(case["expected"])
        except (ValueError, SyntaxError):
            row["ok"] = False
    results.append(row)
print(json.dumps({"results": results, "printed": "".join(printed)[-1000:]}, ensure_ascii=False))
'''


def grader_input(exercise: Exercise, per_test: float) -> str:
    return json.dumps({"child": _CHILD, "function": exercise.function, "per_test": per_test,
                       "tests": [t.model_dump() for t in exercise.tests]}, ensure_ascii=False)


@dataclass
class CheckReport:
    passed: int
    total: int
    results: list[dict] = field(default_factory=list)
    error: str = ""          # import xətası, vaxt həddi, konteyner xətası
    stdout: str = ""         # tələbənin öz print-ləri

    @property
    def score(self) -> float:
        return round(self.passed / self.total, 3) if self.total else 0.0

    def summary(self) -> str:
        lines = [f"Testlər: {self.passed}/{self.total} keçdi"]
        if self.error:
            lines.append(f"Xəta: {self.error}")
        for r in self.results if not self.error else []:   # ümumi xəta hər testdə təkrarlanmır
            if not r["ok"]:
                detail = r.get("error") or f"gözlənilən {r['expected']}, alınan {r.get('got')}"
                lines.append(f"- «{r['name']}»: {detail}")
        return "\n".join(lines)


def parse_run(exercise: Exercise, run: RunResult) -> CheckReport:
    total = len(exercise.tests)
    if run.timed_out:
        return CheckReport(0, total, error="Vaxt həddi aşıldı (sonsuz dövr ola bilər)")
    try:
        data = json.loads(run.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        reason = "yaddaş həddi aşıldı" if run.exit_code == 137 else (run.stderr.strip()[-300:] or "nəticə yoxdur")
        return CheckReport(0, total, error=f"Yoxlama işləmədi: {reason}")
    results = data["results"]
    errors = {r.get("error", "") for r in results}
    common = next(iter(errors)) if len(errors) == 1 and "" not in errors else ""
    return CheckReport(sum(r["ok"] for r in results), total, results, stdout=data.get("printed", ""),
                      error=f"Kod işləmədi: {common}" if common and len(results) > 1 else "")


def run_tests(exercise: Exercise, code: str, *, runner=run_python, timeout: float = 20.0,
              per_test: float = 3.0) -> CheckReport:
    return parse_run(exercise, runner({"solution.py": code}, GRADER, timeout=timeout,
                                      stdin=grader_input(exercise, per_test)))
