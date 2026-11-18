"""evals.sehv: golden dəstdə produksiya yolunun metrikaları (model saxtadır, sympy realdır)."""

import json

from evals import sehv

GOLDEN = sehv.load_golden()


class OracleBackend:
    """Golden etiketini qaytarır; `flip_correct` düzgün həllərə də «1-ci addım» deyir (yalançı həyəcan)."""

    name = "oracle"

    def __init__(self, flip_correct=False):
        self.by_problem = {(r["problem"], tuple(r["steps"])): r for r in GOLDEN}
        self.flip_correct = flip_correct

    def generate(self, domain, problem, steps):
        rec = self.by_problem[(problem, tuple(steps))]
        step, code = rec["wrong_step"], rec["error_type"]
        if step is None and self.flip_correct:
            step, code = 1, None
        return json.dumps({"wrong_step": step, "error_type": code, "explanation": "x"}, ensure_ascii=False)

    def null_prob(self, domain, problem, steps):
        return None


def test_golden_shape():
    assert len(GOLDEN) == 100 and {r["domain"] for r in GOLDEN} == {"riyaziyyat", "mentiq"}


def test_sympy_only_never_false_alarms_and_leaves_logic_unknown():
    report = sehv.evaluate(GOLDEN)["sympy"]
    assert report["hamısı"]["false_alarm"] == 0 and report["hamısı"]["missed"] == 0
    assert report["mentiq"]["unknown"] == 1.0
    assert report["riyaziyyat"]["step_acc"] >= 0.8


def test_oracle_model_is_perfect():
    reports = sehv.evaluate(GOLDEN, OracleBackend())
    for mode in ("model", "model+sympy"):
        r = reports[mode]["hamısı"]
        assert r["step_acc"] == 1 and r["detect_acc"] == 1 and r["false_alarm"] == 0 and r["unknown"] == 0
        assert r["type_macro_f1"] == 1


def test_sympy_veto_cuts_false_alarms_on_math():
    reports = sehv.evaluate(GOLDEN, OracleBackend(flip_correct=True))
    assert reports["model"]["hamısı"]["false_alarm"] == 1
    assert reports["model+sympy"]["riyaziyyat"]["false_alarm"] < reports["model"]["riyaziyyat"]["false_alarm"]
    assert reports["model+sympy"]["mentiq"]["false_alarm"] == 1  # məntiqi sympy yoxlaya bilmir


def test_report_and_cli(tmp_path, capsys):
    out = tmp_path / "r.md"
    assert sehv.main(["--out", str(out)]) == 0
    assert "| sympy | hamısı | 100 |" in capsys.readouterr().out
    assert out.read_text(encoding="utf-8").startswith("# Səhv Detektivi eval")
