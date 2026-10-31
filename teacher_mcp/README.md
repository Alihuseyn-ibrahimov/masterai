# MasterAI müəllim MCP serveri

Claude Desktop-dan (və ya başqa MCP klientindən) MasterAI siniflərini idarə etmək üçün.
Server **sizin kompüterinizdə** işləyir və saytın API-sini sizin hesabınızla çağırır:
saytda edə bilmədiyiniz heç nəyi edə bilmir.

## Nə soruşa bilərsiniz

- «Siniflərimi göstər»
- «Sinif 1-ə sabah saat 10-da 90 dəqiqəlik Konstitusiya dərsi qoy, sinifdə olacaq»
- «Dünənki dərsin mətnindən qanunvericilik üzrə 10 sual hazırla»
- «Son dərsə kim gəlmədi?»
- «Konstitusiya bankını AI komandası ilə yoxla, problemli sualları de»
- «Bu bankı Sinif 1-ə 10 noyabra qədər ev tapşırığı ver»

| Alət | Nə edir |
|---|---|
| `list_classes` | Qrup çatları (siniflər) |
| `list_lessons` | Dərslər, sinif üzrə də |
| `schedule_lesson` | Yeni dərs (onlayn / sinifdə) |
| `lesson_transcript` | Dərsin mətni (səs + lövhə) |
| `quiz_from_lesson` | Dərs mətnindən sual bankı + konspekt |
| `lesson_attendance` | Gələnlər / gəlməyənlər |
| `list_question_banks` | Sual bankları |
| `bank_questions` | Bankın sualları, düzgün cavabla |
| `review_bank` | AI yoxlama komandası (başlat / nəticə) |
| `bank_summary` | Konspekt |
| `assign_homework` | Ev tapşırığı ver |

## Quraşdırma

1. Python 3.11+ və repo: `pip install -r requirements.txt`
2. Claude Desktop → Settings → Developer → Edit Config, `claude_desktop_config.json`-a əlavə edin:

```json
{
  "mcpServers": {
    "masterai": {
      "command": "C:\\yol\\masterai\\.venv\\Scripts\\python.exe",
      "args": ["-m", "teacher_mcp.server"],
      "cwd": "C:\\yol\\masterai",
      "env": {
        "MASTERAI_EMAIL": "muellim@example.com",
        "MASTERAI_PASSWORD": "..."
      }
    }
  }
}
```

3. Claude Desktop-u yenidən açın. Alətlər çəkic ikonunda görünür.

Şifrə əvəzinə `MASTERAI_TOKEN` verə bilərsiniz (90 gün keçərlidir).
Lokal sınaq üçün `MASTERAI_API=http://127.0.0.1:8125`.

**Diqqət:** konfiqurasiya faylında şifrə açıq yazılır. Faylı paylaşmayın.

## Necə sınanıb

`tests/test_teacher_mcp.py` alətləri real FastAPI tətbiqinə qarşı çağırır:
giriş, dərs planlama (Bakı vaxtı → UTC), davamiyyət, banklar, xətalar,
tələbə hesabının müəllim əməliyyatına 403 alması.
