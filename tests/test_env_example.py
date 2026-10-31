"""Server və pipeline-ın oxuduğu HƏR mühit dəyişəni `.env.example`-də olmalıdır (gün 21).

Tapıldı: LiveKit açarları (gün 2) və dörd baza yolu nümunədə yox idi. Yeni serverdə
`.env`-i nümunədən dolduran adam videonun niyə 503 verdiyini kodu oxumadan bilməzdi,
yolu yazılmayan baza isə `data/`-dan kənarda yaranar və backup onu görməzdi.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_READ = re.compile(r"""(?:environ|env)\.get\(\s*["']([A-Z][A-Z0-9_]+)["']|getenv\(\s*["']([A-Z][A-Z0-9_]+)["']"""
                   r"""|environ\[\s*["']([A-Z][A-Z0-9_]+)["']\s*\]""")


def env_names() -> set[str]:
    names = set()
    for folder in ("server", "pipeline"):
        for path in (ROOT / folder).rglob("*.py"):
            for match in _READ.finditer(path.read_text(encoding="utf-8")):
                names.add(next(g for g in match.groups() if g))
    return names


def test_every_setting_is_documented():
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", example, re.MULTILINE))
    names = env_names()
    assert {"LIVEKIT_URL", "GROQ_API_KEY", "LESSONS_DB_PATH"} <= names  # regex işləyir
    assert sorted(names - documented) == []


def test_every_db_path_lives_in_data_dir():
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    for name, value in re.findall(r"^([A-Z_]+_DB_PATH)=(\S+)", example, re.MULTILINE):
        assert value.startswith("/opt/masterai/data/"), name
