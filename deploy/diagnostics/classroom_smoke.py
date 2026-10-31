"""Canlı serverdə MasterAI Classroom-un uc-uca yoxlaması (gün 14).

Müəllim hesabı ilə REAL API-yə qarşı bütün dərs zəncirini bir-bir keçir və
hər addımın nəticəsini yazır:

    sinif → dərs → başla → video tokeni → QR → lövhə şəkli (OCR) → [səs (Whisper)]
    → dərs mətni → quiz + konspekt (AI) → AI yoxlama komandası → AI tutor → dərsi bitir

Real tələbələrin sinfinə toxunmur: «[Yoxlama] Smoke sinfi» adlı ayrıca qrup
yaradır (və ya növbəti işlərdə onu təkrar işlədir). Konspekt dərc OLUNMUR,
tapşırıq təyin OLUNMUR - heç bir tələbə bu dərsi görmür.

Serverdə:

    cd /opt/masterai
    MASTERAI_EMAIL=... MASTERAI_PASSWORD=... .venv/bin/python deploy/diagnostics/classroom_smoke.py

Seçimlər: `--api` (defolt produksiya), `--token` (e-poçt/şifrə əvəzinə),
`--audio FAYL` (real səs yazısı ilə Whisper-i də yoxla), `--skip-ai`
(yalnız AI-sız addımlar). Bütün addımlar keçsə çıxış kodu 0-dır.

Yalnız stdlib + Pillow (lövhə şəkli çəkmək üçün): heç bir əlavə paket yox.
"""

from __future__ import annotations

import argparse
import glob
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

DEFAULT_API = "https://masterai.prdostu.com"
SMOKE_CLASS = "[Yoxlama] Smoke sinfi"

# Lövhəyə yazılan mətn: quiz üçün ≥300 simvol olmalıdır, ə/ö/ü/ş/ç/ğ/ı OCR-i yoxlayır.
BOARD_LINES = [
    "Mövzu: Azərbaycan Respublikasının Konstitusiyası",
    "Konstitusiya 1995-ci il noyabrın 12-də",
    "referendum yolu ilə qəbul edilib.",
    "Milli Məclis 125 deputatdan ibarətdir,",
    "deputatlar beş il müddətinə seçilir.",
    "Prezident yeddi il müddətinə seçilir.",
    "Qanunvericilik hakimiyyəti: Milli Məclis.",
    "İcra hakimiyyəti: Azərbaycan Prezidenti.",
    "Məhkəmə hakimiyyəti: məhkəmələr.",
    "Konstitusiya ən yüksək hüquqi qüvvəyə malikdir.",
]
TUTOR_QUESTION = "Milli Məclis neçə deputatdan ibarətdir?"
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
]


class StepFailed(Exception):
    pass


class Api:
    def __init__(self, base: str, token: str | None = None) -> None:
        self.base = base.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, body=None, *, data: bytes | None = None,
                content_type: str | None = None, expect=(200, 201, 202, 204)):
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            content_type = "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        status, raw = self._send(method, path, data, headers)
        payload = json.loads(raw) if raw and raw[:1] in (b"{", b"[") else raw.decode("utf-8", "replace")
        if status not in expect:
            detail = payload.get("detail") if isinstance(payload, dict) else payload
            raise StepFailed(f"{method} {path} → {status}: {str(detail)[:200]}")
        return status, payload

    def _send(self, method: str, path: str, data: bytes | None, headers: dict) -> tuple[int, bytes]:
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as err:
            return err.code, err.read()

    def upload(self, path: str, fields: dict, file_field: str, filename: str, content: bytes,
               mime: str, expect=(202,)):
        boundary = uuid.uuid4().hex
        parts = []
        for name, value in fields.items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
                         .encode("utf-8"))
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
                     f'filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode("utf-8") + content + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        return self.request("POST", path, data=b"".join(parts),
                            content_type=f"multipart/form-data; boundary={boundary}", expect=expect)


def board_image() -> bytes:
    """Lövhəyə bənzər şəkil: ağ fon, iri qara hərflər."""
    from PIL import Image, ImageDraw, ImageFont

    font_path = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)
    if font_path is None:
        found = glob.glob("/usr/share/fonts/**/*Sans*.ttf", recursive=True)
        font_path = found[0] if found else None
    if font_path is None:
        raise StepFailed("serverdə TTF şrift tapılmadı (apt install fonts-dejavu-core)")
    font = ImageFont.truetype(font_path, 44)
    image = Image.new("RGB", (1600, 120 + 70 * len(BOARD_LINES)), "white")
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(BOARD_LINES):
        draw.text((60, 60 + 70 * i), line, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def wait_for(fetch, done, *, timeout: float, every: float = 3.0):
    deadline = time.monotonic() + timeout
    while True:
        value = fetch()
        if done(value):
            return value
        if time.monotonic() > deadline:
            raise StepFailed(f"{int(timeout)} saniyədə hazır olmadı")
        time.sleep(every)


class Smoke:
    def __init__(self, api: Api, *, audio: str | None, skip_ai: bool, timeout: float, out=print) -> None:
        self.api, self.audio, self.skip_ai, self.timeout, self.out = api, audio, skip_ai, timeout, out
        self.results: list[tuple[str, bool, str]] = []
        self.lesson_id: int | None = None
        self.bank_id: int | None = None

    def step(self, name: str, fn, *, required: bool = True):
        started = time.monotonic()
        try:
            note = fn() or ""
            ok = True
        except StepFailed as exc:
            note, ok = str(exc), False
        except Exception as exc:  # noqa: BLE001 - gözlənilməz xəta da addım nəticəsidir
            note, ok = f"{type(exc).__name__}: {exc}", False
        seconds = time.monotonic() - started
        self.results.append((name, ok, note))
        self.out(f"{'✔' if ok else '✘'} {name:<28} {seconds:5.1f} san  {note}")
        if not ok and required:
            raise StepFailed(name)
        return ok

    # ---- addımlar ----

    def login(self, email: str | None, password: str | None):
        if self.api.token:
            return "tokenlə (müəllim yoxlaması dərs yaradanda)"
        if not (email and password):
            raise StepFailed("MASTERAI_EMAIL və MASTERAI_PASSWORD (və ya --token) lazımdır")
        _, data = self.api.request("POST", "/auth/login", {"email": email, "password": password})
        self.api.token = data["token"]
        if not data["user"].get("is_teacher"):
            raise StepFailed("bu hesab müəllim deyil")
        return data["user"].get("display_name", "")

    def smoke_class(self):
        _, chats = self.api.request("GET", "/chats")
        chat = next((c for c in chats if c["kind"] == "group" and c.get("name") == SMOKE_CLASS), None)
        if chat is None:
            _, chat = self.api.request("POST", "/chats", {"kind": "group", "name": SMOKE_CLASS})
            self.chat_id = chat["id"]
            return f"yaradıldı (#{chat['id']})"
        self.chat_id = chat["id"]
        return f"mövcud (#{chat['id']})"

    def create_lesson(self):
        stamp = datetime.now(timezone.utc)
        _, lesson = self.api.request("POST", f"/chats/{self.chat_id}/lessons", {
            "title": f"[Yoxlama] {stamp:%Y-%m-%d %H:%M}",
            "starts_at": (stamp + timedelta(minutes=1)).isoformat(),
            "duration_min": 30, "mode": "online",
        })
        self.lesson_id = lesson["id"]
        return f"dərs #{lesson['id']}"

    def start_lesson(self):
        _, lesson = self.api.request("POST", f"/live/lessons/{self.lesson_id}/start")
        if lesson["status"] != "live":
            raise StepFailed(f"status {lesson['status']}")
        return "canlı"

    def video_token(self):
        status, data = self.api.request("POST", f"/me/lessons/{self.lesson_id}/video", expect=(200, 503))
        if status == 503:
            raise StepFailed("LiveKit açarları .env-də yoxdur")
        if not (data.get("token") and data.get("url", "").startswith("wss://")):
            raise StepFailed("token və ya wss:// ünvanı yoxdur")
        return f"otaq {data['room']}"

    def qr(self):
        _, data = self.api.request("GET", f"/live/lessons/{self.lesson_id}/qr")
        if "<svg" not in data.get("svg", "") or f"id={self.lesson_id}" not in data.get("url", ""):
            raise StepFailed("SVG və ya link səhvdir")
        return f"kod {data['expires_in']} san keçərli"

    def _transcript(self):
        return self.api.request("GET", f"/live/lessons/{self.lesson_id}/transcript")[1]

    def board(self):
        self.api.upload(f"/live/lessons/{self.lesson_id}/board", {}, "image", "board.png",
                        board_image(), "image/png")
        data = wait_for(self._transcript,
                        lambda t: any(s["kind"] == "board" and s["status"] in ("ready", "failed")
                                      for s in t["segments"]), timeout=120)
        segment = next(s for s in data["segments"] if s["kind"] == "board")
        if segment["status"] != "ready":
            raise StepFailed(f"OCR uğursuz: {segment.get('error')}")
        text = data["text"]
        letters = [ch for ch in "əöüşçğı" if ch in text.lower()]
        hits = sum(word in text for word in ("Konstitusiya", "Məclis", "Prezident", "125", "1995"))
        if hits < 3:
            raise StepFailed(f"OCR mətni zəifdir ({hits}/5 açar söz): {text[:80]!r}")
        return f"{len(text)} simvol, {hits}/5 açar söz, hərflər: {''.join(letters) or 'yox'}"

    def audio_part(self):
        with open(self.audio, "rb") as fh:
            content = fh.read()
        name = os.path.basename(self.audio)
        self.api.upload(f"/live/lessons/{self.lesson_id}/audio", {"seq": "0"}, "audio", name, content,
                        "audio/webm" if name.endswith(".webm") else "application/octet-stream")
        data = wait_for(self._transcript,
                        lambda t: any(s["kind"] == "audio" and s["status"] in ("ready", "failed")
                                      for s in t["segments"]), timeout=300, every=5)
        segment = next(s for s in data["segments"] if s["kind"] == "audio")
        if segment["status"] != "ready":
            raise StepFailed(f"Whisper uğursuz: {segment.get('error')}")
        # Səs (seq 0) mətndə lövhədən ƏVVƏL gəlir.
        spoken = data["text"].split("Lövhədən:")[0].strip()
        if not spoken:
            raise StepFailed("Whisper boş mətn qaytardı")
        return f"{len(spoken)} simvol: {spoken[:60]!r}"

    def transcript_long_enough(self):
        text = self._transcript()["text"]
        if len(text) < 300:
            raise StepFailed(f"dərs mətni {len(text)} simvol (quiz üçün ≥300)")
        return f"{len(text)} simvol"

    def quiz(self):
        _, lesson = self.api.request("POST", f"/live/lessons/{self.lesson_id}/question-set",
                                     {"subject": "qanunvericilik", "question_count": 5, "make_summary": True})
        self.bank_id = lesson["question_set_id"]
        bank = wait_for(lambda: self.api.request("GET", f"/live/question-sets/{self.bank_id}")[1],
                        lambda b: b["status"] != "processing", timeout=self.timeout, every=5)
        if bank["status"] != "ready":
            raise StepFailed(f"bank {bank['status']}: {bank.get('error')}")
        _, questions = self.api.request("GET", f"/live/question-sets/{self.bank_id}/questions")
        if len(questions) < 3:
            raise StepFailed(f"cəmi {len(questions)} sual")
        return f"bank #{self.bank_id}, {len(questions)} sual, məs. {questions[0]['question'][:50]!r}"

    def summary(self):
        data = wait_for(lambda: self.api.request("GET", f"/live/question-sets/{self.bank_id}/summary",
                                                 expect=(200, 404))[1],
                        lambda s: isinstance(s, dict) and s.get("status") in ("ready", "failed"),
                        timeout=self.timeout, every=5)
        if data["status"] != "ready":
            raise StepFailed(f"konspekt uğursuz: {data.get('error')}")
        return f"{data['content'].get('title', '')[:50]!r} (dərc OLUNMADI)"

    def review(self):
        self.api.request("POST", f"/live/question-sets/{self.bank_id}/review", expect=(202,))
        data = wait_for(lambda: self.api.request("GET", f"/live/question-sets/{self.bank_id}/review")[1],
                        lambda r: r["status"] in ("ready", "failed"), timeout=self.timeout, every=5)
        if data["status"] != "ready":
            raise StepFailed(f"yoxlama uğursuz: {data.get('error')}")
        verdicts = [item["verdict"] for item in data["items"]]
        if verdicts and all(v == "unchecked" for v in verdicts):
            raise StepFailed("heç bir sual yoxlanmadı (agentlər cavab vermədi)")
        return " · ".join(f"{v} {verdicts.count(v)}" for v in ("ok", "fix", "unchecked"))

    def tutor(self):
        _, reply = self.api.request("POST", "/me/tutor/ask",
                                    {"question": TUTOR_QUESTION, "lesson_id": self.lesson_id})
        if reply["kind"] != "answer" or "125" not in reply["answer"]:
            raise StepFailed(f"{reply['kind']}: {reply['answer'][:80]!r}")
        return f"{reply['answer'][:70]!r}"

    def end_lesson(self):
        self.api.request("POST", f"/live/lessons/{self.lesson_id}/end")
        return "bitdi"

    # ---- axın ----

    def run(self, email: str | None, password: str | None) -> bool:
        try:
            self.step("Giriş (müəllim)", lambda: self.login(email, password))
            self.step("Yoxlama sinfi", self.smoke_class)
            self.step("Dərs yarat", self.create_lesson)
            self.step("Dərsi başlat", self.start_lesson)
            self.step("Video tokeni (LiveKit)", self.video_token, required=False)
            self.step("QR davamiyyət", self.qr, required=False)
            self.step("Lövhə şəkli → mətn", self.board, required=False)
            if self.audio:
                self.step("Səs → mətn (Whisper)", self.audio_part, required=False)
            if not self.skip_ai:
                self.step("Dərs mətni ≥300 simvol", self.transcript_long_enough)
                self.step("Quiz (AI)", self.quiz)
                self.step("Konspekt (AI)", self.summary, required=False)
                self.step("AI yoxlama komandası", self.review, required=False)
                self.step("AI tutor", self.tutor, required=False)
        except StepFailed:
            pass
        finally:
            if self.lesson_id is not None:
                self.step("Dərsi bitir", self.end_lesson, required=False)
        failed = [name for name, ok, _ in self.results if not ok]
        self.out("")
        self.out(f"Nəticə: {len(self.results) - len(failed)}/{len(self.results)} addım keçdi"
                 + (f" · uğursuz: {', '.join(failed)}" if failed else ""))
        return not failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MasterAI Classroom uc-uca yoxlaması")
    parser.add_argument("--api", default=os.environ.get("MASTERAI_API", DEFAULT_API))
    parser.add_argument("--token", default=os.environ.get("MASTERAI_TOKEN"))
    parser.add_argument("--audio", help="Whisper üçün səs faylı (webm/mp3/m4a/wav)")
    parser.add_argument("--skip-ai", action="store_true", help="AI addımlarını keç")
    parser.add_argument("--timeout", type=float, default=300, help="AI addımı üçün maks. saniyə")
    args = parser.parse_args(argv)
    smoke = Smoke(Api(args.api, args.token), audio=args.audio, skip_ai=args.skip_ai, timeout=args.timeout)
    ok = smoke.run(os.environ.get("MASTERAI_EMAIL"), os.environ.get("MASTERAI_PASSWORD"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
