"""MasterAI müəllim MCP serveri (MasterAI Classroom, gün 11).

Müəllim Claude Desktop-dan (və ya istənilən MCP klientindən) öz
siniflərini idarə edir: «Sabah saat 10-a Konstitusiya dərsi qoy»,
«dünənki dərsin mətnindən 10 suallıq quiz hazırla», «kim gəlmədi?».

Server MÜƏLLİMİN KOMPÜTERİNDƏ işləyir (stdio) və MasterAI-nin MÖVCUD
REST API-sini müəllimin öz tokeni ilə çağırır. Yəni:
- yeni icazə yolu YOXDUR: MCP müəllimin saytda edə bildiyindən artığını
  edə bilmir (kurs sərhədi, müəllim qapısı serverdə yoxlanır);
- VPS-ə heç nə əlavə olunmur, nginx dəyişmir.

Quraşdırma (Claude Desktop `claude_desktop_config.json`):

    {"mcpServers": {"masterai": {
        "command": "python", "args": ["-m", "teacher_mcp.server"],
        "cwd": "/yol/masterai",
        "env": {"MASTERAI_EMAIL": "...", "MASTERAI_PASSWORD": "..."}}}}

`MASTERAI_TOKEN` verilsə e-poçt/şifrə lazım deyil. `MASTERAI_API`
defolt produksiyadır (`https://masterai.prdostu.com`).
"""

from __future__ import annotations

import os
from datetime import datetime

import httpx
from mcp.server.fastmcp import FastMCP

DEFAULT_API = "https://masterai.prdostu.com"
SUBJECTS = {
    "mentiq": "Məntiq", "informatika": "İnformatika", "dunyagorusu": "Dünyagörüşü",
    "azerbaycan_dili": "Azərbaycan dili", "qanunvericilik": "Qanunvericilik", "xarici_dil": "Xarici dil",
}
MAX_TRANSCRIPT_CHARS = 20_000


class MasterAIError(Exception):
    """API xətası - mətni Claude-a olduğu kimi göstərilir."""


class MasterAIClient:
    def __init__(self, base_url: str, *, token: str | None = None, email: str | None = None,
                 password: str | None = None, http: httpx.Client | None = None) -> None:
        # `http` testdə verilir (FastAPI TestClient da httpx.Client-dir).
        self._http = http or httpx.Client(base_url=base_url.rstrip("/"), timeout=60)
        self._token, self._email, self._password = token, email, password

    @classmethod
    def from_env(cls) -> "MasterAIClient":
        return cls(os.environ.get("MASTERAI_API", DEFAULT_API), token=os.environ.get("MASTERAI_TOKEN"),
                   email=os.environ.get("MASTERAI_EMAIL"), password=os.environ.get("MASTERAI_PASSWORD"))

    def _auth(self) -> dict:
        if not self._token:
            if not (self._email and self._password):
                raise MasterAIError("MASTERAI_TOKEN və ya MASTERAI_EMAIL + MASTERAI_PASSWORD təyin edilməyib.")
            r = self._http.post("/auth/login", json={"email": self._email, "password": self._password})
            if r.status_code != 200:
                raise MasterAIError(f"Giriş alınmadı: {_detail(r)}")
            self._token = r.json()["token"]
        return {"Authorization": f"Bearer {self._token}"}

    def call(self, method: str, path: str, **kwargs):
        r = self._http.request(method, path, headers=self._auth(), **kwargs)
        if r.status_code >= 400:
            raise MasterAIError(f"{r.status_code}: {_detail(r)}")
        return r.json() if r.content else None


def _detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except ValueError:
        detail = None
    if isinstance(detail, list):  # FastAPI validasiya xətası
        detail = "; ".join(str(d.get("msg")) for d in detail if isinstance(d, dict))
    return str(detail or response.text[:200] or response.reason_phrase)


def build_server(client: MasterAIClient) -> FastMCP:
    mcp = FastMCP("masterai", instructions=(
        "MasterAI müəllim alətləri. Müəllim Azərbaycan dilində yazır, cavabı da Azərbaycan dilində ver. "
        "Vaxtlar ISO 8601 formatındadır (saat qurşağı ilə, Bakı +04:00). Dərs və bank ID-lərini təxmin "
        "etmə: əvvəl list_classes, list_lessons və ya list_question_banks çağır."
    ))

    @mcp.tool()
    def list_classes() -> list[dict]:
        """Müəllimin qrup çatları (sinifləri): id, ad, dəvət kodu."""
        return [{"id": c["id"], "name": c["name"], "invite_code": c.get("invite_code")}
                for c in client.call("GET", "/chats") if c["kind"] == "group"]

    @mcp.tool()
    def list_lessons(chat_id: int | None = None) -> list[dict]:
        """Dərslər (yaxın tarixdən). chat_id verilsə yalnız o sinfin dərsləri."""
        path = f"/chats/{chat_id}/lessons" if chat_id else "/me/lessons"
        return [{k: lesson.get(k) for k in ("id", "chat_id", "chat_name", "title", "starts_at", "duration_min",
                                            "mode", "status", "question_set_id")}
                for lesson in client.call("GET", path)]

    @mcp.tool()
    def schedule_lesson(chat_id: int, title: str, starts_at: str, duration_min: int = 90,
                        mode: str = "online", description: str = "") -> dict:
        """Sinfə yeni dərs qoyur. starts_at: ISO 8601, məs. 2026-11-03T10:00:00+04:00.
        mode: "online" (video dərs) və ya "offline" (sinifdə, QR davamiyyət)."""
        try:
            datetime.fromisoformat(starts_at)
        except ValueError as exc:
            raise MasterAIError("starts_at ISO 8601 formatında olmalıdır, məs. 2026-11-03T10:00:00+04:00") from exc
        return client.call("POST", f"/chats/{chat_id}/lessons", json={
            "title": title, "starts_at": starts_at, "duration_min": duration_min, "mode": mode,
            "description": description})

    @mcp.tool()
    def lesson_transcript(lesson_id: int) -> dict:
        """Dərsin mətni (səs yazısından Whisper + lövhə şəkillərindən OCR)."""
        data = client.call("GET", f"/live/lessons/{lesson_id}/transcript")
        text = data.get("text") or ""
        return {"lesson_id": lesson_id, "segments": len(data.get("segments", [])),
                "text": text[:MAX_TRANSCRIPT_CHARS], "truncated": len(text) > MAX_TRANSCRIPT_CHARS}

    @mcp.tool()
    def quiz_from_lesson(lesson_id: int, subject: str, question_count: int = 10, make_summary: bool = True) -> dict:
        """Dərs mətnindən sual bankı (və konspekt) hazırlatdırır. Fon işidir: bir neçə dəqiqədən
        sonra list_question_banks ilə yoxla. subject: mentiq, informatika, dunyagorusu,
        azerbaycan_dili, qanunvericilik, xarici_dil."""
        if subject not in SUBJECTS:
            raise MasterAIError(f"Naməlum fənn: {subject}. Mümkün: {', '.join(SUBJECTS)}")
        lesson = client.call("POST", f"/live/lessons/{lesson_id}/question-set", json={
            "subject": subject, "question_count": question_count, "make_summary": make_summary})
        return {"lesson_id": lesson["id"], "question_set_id": lesson.get("question_set_id"),
                "message": "Sual bankı hazırlanır."}

    @mcp.tool()
    def lesson_attendance(lesson_id: int) -> dict:
        """Dərsə kim gəlib, kim gəlməyib."""
        rows = client.call("GET", f"/live/lessons/{lesson_id}/attendance")
        return {"present": [r["display_name"] for r in rows if r["present"]],
                "absent": [r["display_name"] for r in rows if not r["present"]]}

    @mcp.tool()
    def list_question_banks() -> list[dict]:
        """Müəllimin sual bankları: id, başlıq, fənn, status (processing/ready/failed), sual sayı."""
        return [{"id": b["id"], "title": b["title"], "subject": SUBJECTS.get(b["subject"], b["subject"]),
                 "status": b["status"], "question_count": b["question_count"], "error": b.get("error")}
                for b in client.call("GET", "/live/question-sets")]

    @mcp.tool()
    def bank_questions(question_set_id: int) -> list[dict]:
        """Bankın sualları, düzgün cavab və izahla (yalnız müəllim görür)."""
        return [{"id": q["id"], "question": q["question"], "options": q["options"],
                 "correct": q["options"][q["correct_index"]], "explanation": q["explanation"],
                 "difficulty": q.get("difficulty")}
                for q in client.call("GET", f"/live/question-sets/{question_set_id}/questions")]

    @mcp.tool()
    def review_bank(question_set_id: int, start: bool = False) -> dict:
        """AI yoxlama komandası (fakt yoxlayıcı + metodist + redaktor). start=True yeni yoxlama
        başladır, False son nəticəni qaytarır. Təklif sualı DƏYİŞMİR - müəllim saytda tətbiq edir."""
        review = client.call("POST" if start else "GET", f"/live/question-sets/{question_set_id}/review")
        return {"status": review["status"], "error": review.get("error"),
                "needs_attention": [{"question_id": i["question_id"],
                                     "issues": [f"{x['agent_label']}: {x['text']}" for x in i["issues"]],
                                     "has_suggestion": i["suggestion"] is not None}
                                    for i in review.get("items", []) if i["verdict"] == "fix"],
                "ok": sum(1 for i in review.get("items", []) if i["verdict"] == "ok")}

    @mcp.tool()
    def bank_summary(question_set_id: int) -> dict:
        """Bankın materialından hazırlanmış konspekt (xülasə)."""
        summary = client.call("GET", f"/live/question-sets/{question_set_id}/summary")
        return {"status": summary["status"], "published": bool(summary.get("published_at")),
                "content": summary.get("content")}

    @mcp.tool()
    def assign_homework(chat_id: int, question_set_id: int, due_date: str) -> dict:
        """Bankı sinfə ev tapşırığı kimi verir. due_date: YYYY-MM-DD."""
        return client.call("POST", "/homework/assignments", json={
            "chat_id": chat_id, "question_set_id": question_set_id, "due_date": due_date})

    return mcp


def main() -> None:
    build_server(MasterAIClient.from_env()).run()


if __name__ == "__main__":
    main()
