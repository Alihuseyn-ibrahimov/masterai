# MasterAI — n8n/MCP Admin Avtomatlaşdırması (Dizayn Sənədi)

**Tarix:** 2026-09-02
**Status:** Təsdiqlənib (istifadəçi tərəfindən), implementasiya planına keçilir
**Əhatə dairəsi:** Material pipeline-ı artıq backend-də birbaşa işləyir
(`asyncio.to_thread`, real uvicorn-da təsdiqlənib) — bu sənəd pipeline-ı
n8n-ə **köçürmür**. Əvəzinə: (1) uğursuz material üçün Telegram bildirişi,
(2) gündəlik statistika hesabatı — iki minimal admin aləti.

## 1. Problem və məqsəd

`n8n/MCP orkestrasiya` sətri repo xəritəsində "material yükləndikdə
tetiklənən pipeline" kimi planlaşdırılıb, amma material yükləmə
endpoint-i artıq öz spec-i ilə tamamlanıb (backend-daxili fon emalı).
Bu sənəd "admin alətləri" hissəsini konkretləşdirir: admin (istifadəçi
özü) material emalı uğursuz olanda Telegram-da dərhal bilir, gündəlik
də ümumi rəqəmləri görür — heç birini əl ilə DB-yə baxmadan.

## 2. Arxitektura

```
Backend (server/app.py)                    n8n (bu MCP sessiyasındakı instansiya)
─────────────────────────                  ─────────────────────────────────
_process_material() uğursuz olanda    ──POST──▶  Webhook Trigger
  → ADMIN_WEBHOOK_URL-ə fire-and-forget         → Telegram (sendMessage)
    (try/except, heç vaxt material
    emalını bloklamır/pozmur)

GET /admin/stats (X-Admin-Key)        ◀──GET───  Schedule Trigger (gündəlik)
  → JSON: istifadəçi/material/sual/          → HTTP Request (X-Admin-Key)
    quiz/dostluq sayları                      → Telegram (sendMessage, formatlı)
```

İki axın tamamilə müstəqildir — biri backend-dən n8n-ə (push), digəri
n8n-dən backend-ə (pull). Pipeline məntiqi (LLM çağırışları) dəyişmir,
yalnız YAN təsir (side-effect) əlavə olunur.

## 3. Backend dəyişiklikləri (`server/app.py`)

### 3.1. `GET /admin/stats`

```python
class AdminStatsInfo(BaseModel):
    users_total: int
    materials_total: int
    materials_ready: int
    materials_failed: int
    questions_total: int
    quiz_sessions_total: int
    friendships_accepted: int

def require_admin(x_admin_key: str = Header(...)) -> None:
    if x_admin_key != os.environ.get("ADMIN_API_KEY", ""):
        raise HTTPException(403, "Admin açarı səhvdir")

@app.get("/admin/stats", response_model=AdminStatsInfo, dependencies=[Depends(require_admin)])
def admin_stats(...) -> AdminStatsInfo: ...
```

Sayğac sorğuları üçün hər Store-a **minimal** `count_all()`/
`count_by_status()` metodları əlavə olunur (mövcud `list_*`
metodlarının nəticəsinin `len()`-i ilə eyni, amma ayrıca `COUNT(*)`
sorğusu — böyük cədvəllərdə `list_*`-i tam yükləməkdən qaçmaq üçün):
`UserStore.count_all()`, `MaterialStore.count_all()`+
`count_by_status(status)`, `QuestionStore.count_all()`,
`QuizSessionStore.count_all()`, `FriendshipStore.count_by_status(status)`.
`ADMIN_API_KEY` boşdursa (env təyin olunmayıb) — **bütün** çağırışlar
`403` qaytarır (boş = heç kim uyğun gəlmir, "açıq admin" riski yoxdur).

### 3.2. Uğursuz material webhook-u

`_process_material()`-in mövcud uğursuzluq qolunda (sistem mesajından
DƏRHAL SONRA):

```python
if (webhook_url := os.environ.get("ADMIN_WEBHOOK_URL")):
    try:
        async with httpx.AsyncClient(timeout=3) as http:
            await http.post(webhook_url, json={
                "material_id": material_id, "chat_id": chat_id,
                "kind": source.kind, "location": source.location,
                "error": str(exc),
            })
    except Exception:
        pass  # bildiriş uğursuzluğu material emalı nəticəsini POZMUR
```

Fire-and-forget, **cəhd təkrarlanmır** (1 cəhd, 3 saniyə timeout) —
bildiriş itsə belə, əsas nəticə (material `"failed"`, çatda sistem
mesajı) hər halda mövcuddur, admin materialları/statistikanı istənilən
vaxt `GET /admin/stats`/çatdan görə bilər. `ADMIN_WEBHOOK_URL` təyin
olunmayıbsa, çağırış tamamilə keçilir (heç bir xəbərdarlıq/log YOX —
bu, lokal/test mühitlərində defolt haldır).

## 4. n8n workflow-ları

Hər ikisi n8n Workflow SDK ilə real qurulur (bu MCP sessiyasındakı
instansiyada), `test_workflow` ilə manual işə salınıb yoxlanılır,
`publish_workflow` ilə aktivləşdirilir.

### 4.1. "MasterAI — Uğursuz Material Bildirişi"

`Webhook Trigger` (POST, path: `masterai-material-failed`) →
`Telegram` node (`sendMessage`, "Telegram account" kredensialı,
`chat_id` — istifadəçinin verdiyi dəyər birbaşa node parametrinə
yazılır, n8n workflow JSON-unun daxilində saxlanılır, repo-ya
YAZILMIR) — mesaj mətni: material ID, kind, location, xəta mətni.

### 4.2. "MasterAI — Gündəlik Statistika"

`Schedule Trigger` (gündəlik, saat 09:00, Bakı vaxtı — `Asia/Baku`) →
`HTTP Request` (`GET {{ADMIN_STATS_URL}}`, header `X-Admin-Key`) →
`Telegram` node (`sendMessage`, formatlı statistika mətni).

`ADMIN_STATS_URL` hazırkı fazada **placeholder** (backend hələ deploy
olunmayıb, bax bölmə 6) — dəyişən kimi saxlanılır, deploy fazasında
real domenə yenilənəcək.

## 5. Təhlükəsizlik

- `ADMIN_API_KEY` və `ADMIN_WEBHOOK_URL` yalnız env — heç vaxt commit
  edilmir, repo qaydasına uyğun (kök `CLAUDE.md`, "Təhlükəsizlik" bölməsi)
- Webhook Trigger URL-i "gizli" olması ilə minimal qorunur (n8n-in
  təsadüfi path-i) — bu fazada əlavə imza/token yoxdur (əhatə xaricində,
  bax bölmə 7); real risk aşağıdır (material uğursuzluq mətni həssas
  deyil)
- `/admin/stats` header-siz/səhv key ilə HEÇ bir sayğac sızdırmır (403)

## 6. Xəta idarəetməsi və bilinən məhdudiyyət

- Webhook çağırışı uğursuz olsa (n8n əlçatmaz, timeout) — material
  hələ də `"failed"` statusuna keçir və çatda sistem mesajı görünür
  (əsas axın POZULMUR, bax `material-upload-design.md` bölmə 6-nın
  eyni prinsipi: heç vaxt səssiz udulma, AMMA bu YAN təsirin
  uğursuzluğu əsas nəticəni poza bilməz)
- **Bilinən məhdudiyyət:** backend hələ deploy olunmayıb — "Gündəlik
  Statistika" workflow-u `ADMIN_STATS_URL` üçün real ictimai ünvana
  ehtiyac duyur. Bu fazada workflow strukturu qurulur, manual test
  data ilə Telegram-a çatdırma yoxlanılır, amma real `/admin/stats`
  çağırışı yalnız Deploy fazasından sonra tam doğrulana bilər (əvvəlki
  presedentlərə uyğun: pipeline real LLM sınağı, material yükləmə real
  API sınağı — hər ikisi oxşar səbəbdən istifadəçinin öz mühitinə/
  gələcək fazaya saxlanılıb)

## 7. Test strategiyası

- Backend: `test_admin_endpoints.py` — `GET /admin/stats` üçün
  403 (səhv/olmayan key), 200 (düzgün key, rəqəmlərin düzgünlüyü);
  `_process_material` üçün webhook çağırışının edildiyini (mock
  `httpx.AsyncClient.post`) və uğursuzluğunun material nəticəsinə
  TƏSİR ETMƏDİYİNİ təsdiqləyən test
- n8n: hər iki workflow `test_workflow` ilə real manual icra edilir —
  Webhook Trigger üçün nümunə JSON payload göndərilir, Telegram-a
  mesaj getdiyi (n8n execution log-undan) təsdiqlənir; Schedule
  Trigger-in `HTTP Request` addımı bu fazada `ADMIN_STATS_URL`
  yerinə sabit test payload-u qəbul edən müvəqqəti mock URL və ya
  manual "pin data" ilə test edilir (real backend hələ ictimai deyil)

## 8. Əhatə xaricində

- Pipeline-ın özünün n8n-ə köçürülməsi (backend-daxili qalır)
- Tam admin paneli/RBAC (yalnız tək paylaşılan `ADMIN_API_KEY`)
- Webhook imza doğrulaması (HMAC) — risk aşağı olduğu üçün indi əlavə
  olunmur, `masterai/CLAUDE.md`-də "Bilinən risklər" olaraq qeyd olunur
- Digər admin bildirişləri (yeni istifadəçi, hesabat tezliyinin
  konfiqurasiyası UI-dan) — gələcək fazalar
