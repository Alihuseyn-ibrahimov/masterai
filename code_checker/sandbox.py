"""Tələbə kodunu Docker-də təcrid olunmuş işlədir (gün 19).

Tələbə kodu ETİBARSIZDIR: sonsuz dövr, fayl silmə, şəbəkəyə çıxış, yaddaşı
doldurmaq - hamısı mümkündür. Konteyner buna görə ən sərt rejimdədir:

    --network none            şəbəkə yoxdur (məlumat çıxara bilməz)
    --read-only + --tmpfs     fayl sistemi yalnız oxunur, /tmp 16 MB yaddaşda
    -v kod:/work:ro           tələbənin faylları yalnız oxunur
    --memory / --cpus         yaddaş və prosessor həddi (swap da bağlı)
    --pids-limit              «fork bomb» yoxdur
    --user 65534 (nobody)     root deyil
    --cap-drop ALL, no-new-privileges

Vaxt həddi aşılanda konteyner `docker kill` ilə öldürülür (yalnız klient
prosesini öldürmək konteyneri arxada işlək qoyardı).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass

IMAGE = os.environ.get("CODE_CHECKER_IMAGE", "python:3.12-slim")
OUTPUT_LIMIT = 4000


@dataclass
class RunResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _trim(text: str) -> str:
    return text if len(text) <= OUTPUT_LIMIT else text[:OUTPUT_LIMIT] + "\n… (çıxış kəsildi)"


def docker_command(name: str, workdir: str, command: list[str], *, image: str = IMAGE, memory: str = "256m",
                   cpus: str = "0.5", pids: int = 64) -> list[str]:
    return [
        "docker", "run", "--rm", "-i", "--name", name,
        "--network", "none", "--read-only", "--tmpfs", "/tmp:rw,size=16m",
        "--memory", memory, "--memory-swap", memory, "--cpus", cpus, "--pids-limit", str(pids),
        "--user", "65534:65534", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "PYTHONIOENCODING=utf-8",
        "-v", f"{workdir}:/work:ro", "-w", "/work", image, *command,
    ]


def run_in_docker(files: dict[str, str], command: list[str], *, timeout: float = 10.0,
                  image: str = IMAGE, memory: str = "256m", stdin: str = "") -> RunResult:
    name = f"masterai-check-{uuid.uuid4().hex[:12]}"
    with tempfile.TemporaryDirectory(prefix="masterai-code-") as workdir:
        for filename, content in files.items():
            if "/" in filename or filename.startswith("."):
                raise ValueError(f"Yanlış fayl adı: {filename}")
            with open(os.path.join(workdir, filename), "w", encoding="utf-8") as fh:
                fh.write(content)
        os.chmod(workdir, 0o755)
        for filename in files:
            os.chmod(os.path.join(workdir, filename), 0o644)
        try:
            proc = subprocess.run(docker_command(name, workdir, command, image=image, memory=memory),
                                  input=stdin, capture_output=True, text=True, timeout=timeout + 20)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", name], capture_output=True)
            return RunResult(124, "", "Vaxt həddi aşıldı", timed_out=True)
    timed_out = proc.returncode == 124
    return RunResult(proc.returncode, _trim(proc.stdout), _trim(proc.stderr), timed_out=timed_out)


def run_python(files: dict[str, str], script: str, *, timeout: float = 10.0, stdin: str = "") -> RunResult:
    """`script`-i `files` yanında işlədir. Vaxt həddini konteynerin içində `timeout` (coreutils)
    tutur və 124 qaytarır; xaricdəki həd yalnız ehtiyatdır (konteynerin qalxması da vaxt aparır).
    `python -I`: PYTHONPATH və istifadəçi paketləri nəzərə alınmır, skript özü `/work`-u əlavə edir."""
    return run_in_docker({**files, "_run.py": script},
                         ["timeout", "-k", "1", str(max(1, int(timeout))), "python", "-I", "_run.py"],
                         timeout=timeout, stdin=stdin)
