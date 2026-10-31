"""Gün 19: Docker sandbox, tapşırıq testləri, AutoGen komandası və CLI.

Docker testləri Docker işləyirsə keçir (GitHub Actions runner-ində var); AutoGen
testləri `autogen-agentchat` quraşdırılıbsa (requirements-autogen.txt).
"""

import csv
import json

import pytest

from code_checker import cli
from code_checker.exercises import (
    GRADER, CheckReport, grader_input, list_exercises, load_exercise, parse_run, run_tests,
)
from code_checker.sandbox import RunResult, docker_available, docker_command

needs_docker = pytest.mark.skipif(not docker_available(), reason="Docker işləmir")

REFERENCE = {
    "cut_ededlerin_cemi": "def cut_cem(e):\n    return sum(x for x in e if x % 2 == 0)\n",
    "soz_tezliyi": ("import re\ndef soz_tezliyi(m):\n    m = m.replace('I', 'ı').replace('İ', 'i').lower()\n"
                    "    d = {}\n    for w in re.findall(r'\\w+', m):\n        d[w] = d.get(w, 0) + 1\n    return d\n"),
    "minmax_normallasdirma": ("def normallasdir(x):\n    if not x:\n        return []\n    a, b = min(x), max(x)\n"
                              "    return [0.0] * len(x) if a == b else [round((v - a) / (b - a), 3) for v in x]\n"),
}
WRONG = "def cut_cem(e):\n    return sum(x for x in e if x > 0 and x % 2 == 0)\n"


# ---- LLM-siz, Docker-siz --------------------------------------------------------------

def test_exercises_load_and_ids_are_safe():
    ids = {ex.id for ex in list_exercises()}
    assert ids == set(REFERENCE)
    with pytest.raises(KeyError):
        load_exercise("../../server/app")


def test_docker_command_is_locked_down():
    cmd = " ".join(docker_command("n", "/tmp/w", ["python"]))
    for flag in ("--network none", "--read-only", "--cap-drop ALL", "--security-opt no-new-privileges",
                 "--user 65534:65534", "--pids-limit 64", "--memory-swap 256m", "/tmp/w:/work:ro"):
        assert flag in cmd


def test_tests_are_not_in_the_grader_file():
    """Tələbə kodu /work/_run.py-ni oxuya bilir - gözlənilən cavablar orada OLMAMALIDIR."""
    exercise = load_exercise("cut_ededlerin_cemi")
    assert "cut_cem([1, 2, 3, 4])" not in GRADER
    assert "cut_cem([1, 2, 3, 4])" in grader_input(exercise, 3.0)


def test_parse_run_cases():
    exercise = load_exercise("cut_ededlerin_cemi")
    assert parse_run(exercise, RunResult(124, "", "", timed_out=True)).error.startswith("Vaxt həddi")
    assert "yaddaş" in parse_run(exercise, RunResult(137, "", "")).error
    ok = {"name": "x", "ok": True, "expected": "1"}
    bad = {"name": "y", "ok": False, "expected": "2", "got": "3"}
    report = parse_run(exercise, RunResult(0, json.dumps({"results": [ok, bad], "printed": "salam"}), ""))
    assert (report.passed, report.total, report.stdout) == (1, 5, "salam")
    assert "«y»: gözlənilən 2, alınan 3" in report.summary()
    same = {"name": "z", "ok": False, "expected": "1", "error": "NameError: x"}
    report = parse_run(exercise, RunResult(0, json.dumps({"results": [same, same]}), ""))
    assert report.error == "Kod işləmədi: NameError: x" and report.summary().count("NameError") == 1


def test_strip_solution():
    pytest.importorskip("autogen_agentchat")
    from code_checker.team import strip_solution

    full = "Düzəliş:\n```python\ndef cut_cem(e):\n    t = 0\n    for x in e:\n        t += x\n    return t\n```"
    assert "def cut_cem" not in strip_solution(full) and "həlli özün yaz" in strip_solution(full)
    hint = "Bax:\n```python\nx % 2 == 0\n```"
    assert strip_solution(hint) == hint


# ---- Docker sandbox -------------------------------------------------------------------

@needs_docker
@pytest.mark.parametrize("exercise_id", sorted(REFERENCE))
def test_reference_solutions_pass(exercise_id):
    report = run_tests(load_exercise(exercise_id), REFERENCE[exercise_id])
    assert report.passed == report.total, report.summary()


@needs_docker
def test_wrong_solution_and_hostile_code():
    exercise = load_exercise("cut_ededlerin_cemi")
    wrong = run_tests(exercise, WRONG)
    assert wrong.passed == 4 and "mənfi cüt" in wrong.summary()

    loop = run_tests(exercise, "def cut_cem(e):\n    while True:\n        pass\n", per_test=1.0)
    assert loop.passed == 0 and "vaxt" in loop.error

    network = run_tests(exercise, "import socket\nsocket.create_connection(('1.1.1.1', 80), timeout=2)\n"
                                  "def cut_cem(e):\n    return 0\n")
    assert network.passed == 0 and "Network is unreachable" in network.error

    write = run_tests(exercise, "open('/work/x', 'w')\ndef cut_cem(e):\n    return 0\n")
    assert "Read-only file system" in write.error

    memory = run_tests(exercise, "def cut_cem(e):\n    x = bytearray(600 * 1024 * 1024)\n    return 0\n")
    assert memory.passed == 0 and "yaddaş" in memory.error


@needs_docker
def test_student_cannot_forge_results():
    """Tələbə kodu nəticə sətrini çap edib prosesdən çıxsa da, grader ayrı prosesdir."""
    forged = ("import json, os\ndef cut_cem(e):\n"
              "    print(json.dumps({'results': [{'name': 'x', 'ok': True, 'expected': '1'}] * 5}))\n"
              "    os._exit(0)\n")
    assert run_tests(load_exercise("cut_ededlerin_cemi"), forged).passed == 0


# ---- AutoGen komandası (saxta model + saxta sandbox) ---------------------------------------

def _fake_runner(calls):
    def runner(files, script, *, timeout=10, stdin=""):
        calls.append(script)
        if script == GRADER:
            results = [{"name": f"t{i}", "ok": i != 2, "expected": "-2" if i == 2 else "0", "got": "0"}
                       for i in range(5)]
            return RunResult(0, json.dumps({"results": results, "printed": ""}), "")
        return RunResult(0, "cut_cem([-2]) = 0\n", "")
    return runner


def test_autogen_team_reviewer_uses_tool_and_mentor_ends():
    pytest.importorskip("autogen_agentchat")
    from autogen_core import FunctionCall
    from autogen_core.models import CreateResult, RequestUsage
    from autogen_ext.models.replay import ReplayChatCompletionClient

    from code_checker.team import review

    usage = RequestUsage(prompt_tokens=0, completion_tokens=0)
    info = {"vision": False, "function_calling": True, "json_output": False, "family": "unknown",
            "structured_output": False}
    reviewer = ReplayChatCompletionClient([
        CreateResult(finish_reason="function_calls", usage=usage, cached=False,
                     content=[FunctionCall(id="1", name="run_experiment",
                                           arguments=json.dumps({"code_snippet": "from solution import cut_cem\n"
                                                                                 "print(cut_cem([-2]))"}))]),
        "Mənfi cüt ədədlər atılır: şərtdə `x > 0` var.",
    ], model_info=info)
    mentor = ReplayChatCompletionClient([
        "Dövr düzgündür. Mənfi ədədlərə bax.\n```python\ndef cut_cem(e):\n    t = 0\n    for x in e:\n"
        "        t += x\n    return t\n```\nYEKUN"], model_info=info)
    calls = []
    result = review(load_exercise("cut_ededlerin_cemi"), WRONG, reviewer_client=reviewer, mentor_client=mentor,
                    runner=_fake_runner(calls))
    assert result.report.passed == 4                       # bal testlərdəndir
    assert len(calls) == 2 and "print(cut_cem([-2]))" in calls[1]   # alət sandbox-da işlədi
    assert "Mənfi ədədlərə bax" in result.feedback
    assert "YEKUN" not in result.feedback and "def cut_cem" not in result.feedback
    sources = [s for s, _ in result.transcript]
    assert sources[0] == "user" and "yoxlayici" in sources and sources[-1] == "mentor"


# ---- CLI ----------------------------------------------------------------------------------

def test_cli_list(capsys):
    assert cli.main(["list"]) == 0
    assert "cut_ededlerin_cemi" in capsys.readouterr().out


@needs_docker
def test_cli_check_and_batch(tmp_path, capsys):
    good, bad = tmp_path / "ali.py", tmp_path / "veli.py"
    good.write_text(REFERENCE["cut_ededlerin_cemi"], encoding="utf-8")
    bad.write_text(WRONG, encoding="utf-8")
    (tmp_path / "boyuk.py").write_text("#" * 60_000, encoding="utf-8")
    assert cli.main(["check", "--exercise", "cut_ededlerin_cemi", "--file", str(good), "--no-ai"]) == 0
    assert cli.main(["check", "--exercise", "cut_ededlerin_cemi", "--file", str(bad), "--no-ai"]) == 1
    out = tmp_path / "q.csv"
    fake = lambda exercise, code: type("R", (), {"report": CheckReport(5, 5), "feedback": "Əla"})()  # noqa: E731
    assert cli.main(["batch", "--exercise", "cut_ededlerin_cemi", "--dir", str(tmp_path), "--out", str(out)],
                    reviewer=fake) == 0
    rows = {r["student"]: r for r in csv.DictReader(open(out, encoding="utf-8"))}
    assert rows["ali"]["passed"] == "5" and rows["veli"]["passed"] == "4" and "böyük" in rows["boyuk"]["error"]
    assert cli.main(["batch", "--exercise", "cut_ededlerin_cemi", "--dir", str(tmp_path), "--out", str(out),
                     "--ai"], reviewer=fake) == 0
    assert {r["feedback"] for r in csv.DictReader(open(out, encoding="utf-8")) if r["student"] != "boyuk"} == {"Əla"}
