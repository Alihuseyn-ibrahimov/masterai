"""Veb client-i ilə backend arasındakı müqavilə testləri.

İki ayrı şey yoxlanılır:

1. **JS vahid testləri** — `node --test` ilə işə salınır. Node yoxdursa
   test ATLANIR (istifadəçinin Windows mühitində Node olmaya bilər),
   amma bu sandbox-da və CI-da real icra olunur.
2. **Endpoint müqaviləsi** — `api.js`-dəki hər yolun `server/app.py`-də
   HƏQİQƏTƏN mövcud olduğu. Yazı səhvi (`/auth/loginn`) brauzerdə yalnız
   404 kimi görünər və səbəbi aydın olmaz; burada dərhal tutulur.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
APP_PY = ROOT / "server" / "app.py"

_ROUTE_RE = re.compile(r'@app\.(?:get|post|put|patch|delete|websocket)\(\s*"([^"]+)"')
# `request('/auth/login', ...)` və `` `${API_BASE_URL}/health` `` kimi
# çağırışlardakı yolları tutur.
_JS_PATH_RE = re.compile(r"request\(\s*['\"]([^'\"]+)['\"]")


def _backend_routes() -> set[str]:
    return set(_ROUTE_RE.findall(APP_PY.read_text(encoding="utf-8")))


def _js_paths() -> set[str]:
    paths: set[str] = set()
    for js in (WEB / "assets" / "js").glob("*.js"):
        paths.update(_JS_PATH_RE.findall(js.read_text(encoding="utf-8")))
    return paths


class TestEndpointContract:
    def test_backend_routes_were_found(self):
        """Qoruyucu: regex sınıbsa, aşağıdakı test sükutla 'keçər'."""
        assert len(_backend_routes()) > 20

    def test_every_client_path_exists_in_the_backend(self):
        routes = _backend_routes()
        unknown = {path for path in _js_paths() if path not in routes}
        assert not unknown, f"backend-də olmayan yol: {sorted(unknown)}"

    def test_client_paths_were_found(self):
        assert _js_paths(), "api.js-də heç bir endpoint tapılmadı — regex sınıb ola bilər"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node quraşdırılmayıb")
class TestJavaScriptUnitTests:
    def test_node_test_suite_passes(self):
        test_files = sorted((WEB / "tests").glob("*.test.js"))
        assert test_files, "JS test faylı tapılmadı"

        result = subprocess.run(
            ["node", "--test", *[str(p) for p in test_files]],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=120,
        )
        assert result.returncode == 0, (
            "JS testləri uğursuz oldu:\n" + result.stdout[-4000:] + result.stderr[-2000:]
        )
        assert "# fail 0" in result.stdout


class TestSubjectCatalogContract:
    """`subjects.js` iki ayrı mənbə ilə uzlaşmalıdır: backend-in fənn
    siyahısı və dizayn tokenlərindəki rənglər. Biri dəyişib digəri
    dəyişməsə, fənn ya seçilə bilmir, ya rəngsiz görünür — hər ikisi
    sükutla baş verir."""

    SUBJECTS_JS = WEB / "assets" / "js" / "subjects.js"
    STORE_PY = ROOT / "server" / "question_set_store.py"
    TOKENS_CSS = WEB / "assets" / "css" / "tokens.css"

    def _js_subjects(self) -> list[tuple[str, str]]:
        text = self.SUBJECTS_JS.read_text(encoding="utf-8")
        return re.findall(r"key:\s*'([^']+)'.*?cssVar:\s*'([^']+)'", text)

    def _backend_subjects(self) -> list[str]:
        text = self.STORE_PY.read_text(encoding="utf-8")
        block = re.search(r"SUBJECTS\s*=\s*\(([^)]*)\)", text)
        assert block, "question_set_store.py-də SUBJECTS tapılmadı"
        return re.findall(r'"([^"]+)"', block.group(1))

    def test_js_and_backend_subject_keys_match(self):
        assert [key for key, _ in self._js_subjects()] == self._backend_subjects()

    def test_every_subject_has_a_defined_color_token(self):
        tokens = self.TOKENS_CSS.read_text(encoding="utf-8")
        missing = [css_var for _, css_var in self._js_subjects() if f"{css_var}:" not in tokens]
        assert not missing, f"tokens.css-də təyin olunmayan fənn rəngi: {missing}"

    def test_question_count_limits_match_the_backend(self):
        """Formadakı min/maks sual sayı backend-in yoxlaması ilə üst-üstə
        düşməlidir — əks halda istifadəçi 400 xətası alır."""
        app_py = (ROOT / "server" / "app.py").read_text(encoding="utf-8")
        minimum = int(re.search(r"_MIN_QUESTION_COUNT\s*=\s*(\d+)", app_py).group(1))
        maximum = int(re.search(r"_MAX_QUESTION_COUNT\s*=\s*(\d+)", app_py).group(1))
        html = (WEB / "muellim.html").read_text(encoding="utf-8")
        assert f'min="{minimum}"' in html, f"formada min={minimum} yoxdur"
        assert f'max="{maximum}"' in html, f"formada max={maximum} yoxdur"
