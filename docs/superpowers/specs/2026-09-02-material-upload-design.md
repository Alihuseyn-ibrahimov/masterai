# MasterAI — Material Yükləmə Endpoint-i (Dizayn Sənədi)

**Tarix:** 2026-09-02
**Status:** Təsdiqlənib (istifadəçi tərəfindən), implementasiya planına keçilir
**Əhatə dairəsi:** Çata material (sayt linki / PDF / şəkil) yükləmə HTTP
səthi + onu `pipeline.generate_quiz()`-i fon tapşırığı kimi tetikləyən
əlaqə. Bu, "AI sual generasiya pipeline-ı" (birinci spec, tamamlanıb) ilə
"çat infrastrukturu" (Faza A+B, tamamlanıb) arasındakı son körpüdür.

## 1. Problem və məqsəd

Pipeline hazırdır (material→sual), çat hazırdır (mesajlaşma+quiz), amma
onları birləşdirən HTTP səthi yoxdur — hazırda material yalnız Store-lara
birbaşa Python-dan yazılaraq test edilə bilir. Bu sənəd istifadəçinin
real materialı (fayl və ya link) çata necə yükləyəcəyini təsvir edir.

## 2. DB sxem əlavəsi (kiçik)

Mövcud `materials` cədvəlində (Faza 1 backend spec) `label` sütunu
YOXDUR — yalnız `pipeline.models.MaterialSource.label` var idi (heç
yerdə saxlanmırdı). Bu fazada əlavə olunur:

```sql
ALTER TABLE materials ADD COLUMN label TEXT;
```

`MaterialStore.create()` `label: str | None = None` parametri alır,
`get()`/`list_by_chat()` onu da qaytarır. Köhnə sətirlər üçün `NULL` —
geriyə uyğun (mövcud testlər sınmır, `label` sadəcə `None` görünür).

## 3. Arxitektura

```
masterai/server/
  app.py    # +POST /chats/{id}/materials, +GET /chats/{id}/materials
  uploads/     # yüklənən fayllar (.gitignore-da)
```

**Vacib memarlıq qərarı — fon emalı ayrı thread-də:**
`pipeline.generate_quiz()` sinxron və YAVAŞ funksiyadır (LLM/scraping/OCR
şəbəkə çağırışları). Onu birbaşa `async` endpoint-dən çağırmaq bütün
event loop-u (bütün digər HTTP/WS sorğularını) donduraraq bloklayardı.
Həll: `asyncio.to_thread(generate_quiz, ...)` — ayrı thread-də icra
olunur, nəticə hazır olanda `await` ilə geri qayıdır. Bu, Faza B-də
Store-lara əlavə edilən `threading.Lock`/`RLock` sayəsində təhlükəsizdir
— fon thread-i `MaterialStore`/`QuestionStore`-a yazanda kilidlər
qorunma təmin edir.

**Test edilə bilmə üçün:** pipeline çağırışı `Depends()` ilə inject
olunur (`get_material_generator`) — real API açarı olmadan testlərdə
fake (sürətli, sabit nəticəli) funksiya ilə əvəzlənir.

## 4. REST səthi

### `POST /chats/{chat_id}/materials` (multipart/form-data)

Sahələr: `kind` (`"link"|"pdf"|"image"`), `location` (link üçün, `Form`),
`file` (pdf/image üçün, `UploadFile`), `label` (istəyə bağlı ad).

- Auth tələb olunur, çat üzvü olmaq **kifayətdir** (yükləmə icazəsi
  bütün üzvlərə açıqdır — istifadəçinin seçimi)
- `kind="link"` + `location` yoxdur → `400`
- `kind` `pdf`/`image` + `file` yoxdur → `400`
- Fayl ölçüsü `MAX_UPLOAD_BYTES` (20 MB) aşırsa → `413`
- Naməlum `chat_id` → `404`; üzv deyil → `403`
- Fayl varsa: UUID-əsaslı ad (`{uuid4().hex}{uzantı}`) ilə
  `masterai/server/uploads/`-a yazılır — **orijinal fayl adı heç vaxt
  birbaşa fayl sisteminə yazılmır** (path traversal qarşısı)
- `MaterialStore.create(status="processing")` yaradılır
- Fon tapşırığı planlaşdırılır (`asyncio.create_task`,
  `app.state.active_material_tasks[material_id]`-də strong-ref saxlanılır
  — Faza B-dəki `active_quiz_timeouts` ilə eyni naxış)
- **Dərhal `202 Accepted`**, `MaterialInfo(status="processing")` qaytarır

### `GET /chats/{chat_id}/materials`

Çatın materiallarını sadalayır (`MaterialStore.list_by_chat`). Auth+üzvlük
tələb olunur. Tək-material `GET` endpoint-i bu fazada yoxdur — status
dəyişikliyi WS sistem mesajı ilə bildirilir (aşağı bax), siyahı kifayətdir.

## 5. Fon emalı axını

```
_process_material(material_id, chat_id, source, questions_per_chunk, ...):
    try:
        result = await asyncio.to_thread(generator, source, questions_per_chunk)
    except Exception as exc:
        materials.update_status(material_id, "failed")
        sistem mesajı: "Material emalı uğursuz oldu: <səbəb>" → broadcast
        return
    hər mcq üçün: questions.create_from_mcq(material_id, mcq)
    materials.update_status(material_id, "ready")
    sistem mesajı: "Material hazırdır! N sual yaradıldı." → broadcast
```

Sistem mesajları mövcud `MessageStore`/`ConnectionManager`-i işlədir
(`sender_id=None, kind="system"`) — yeni infrastruktur qurulmur.

## 6. Xəta idarəetməsi

- Fayl oxunarkən 20 MB-dan çox məlumat aşkarlansa → dərhal `413`, fayl
  disk-ə YAZILMIR (streamli oxuma limiti ilə yoxlanır, tam yüklənib
  sonra ölçüsünə baxılmır)
- Fon emalı istənilən səbəbdən uğursuz olsa (`IngestionError`,
  `PipelineError`, naməlum istisna) → material `"failed"` statusuna
  keçir, çatda **görünən** sistem mesajı ilə bildirilir — heç vaxt
  səssiz udulmur
- Server prosesi emalı gedərkən yenidən başlasa → planlaşdırılmış fon
  tapşırığı itir, material əbədi `"processing"`-də qalır. Bilinən
  məhdudiyyət (Faza B-nin timeout-suz-server-restart-riskinə bənzər) —
  bərpa mexanizmi əhatə xaricindədir

## 7. Test strategiyası

- `test_material_endpoints.py`:
  - REST validasiya: 403 (üzv deyil), 404 (naməlum çat), 400 (əskik
    sahə), 413 (böyük fayl)
  - Uğurlu axın: fake generator (sabit `PipelineResult` qaytarır) ilə
    yüklə → dərhal `202`+`"processing"` → qısa gözləmədən sonra
    (`MaterialStore.get()` pollinq, dildostu-nun real-gözləmə naxışına
    bənzər, maks. ~1san) `"ready"`, suallar `QuestionStore`-da, sistem
    mesajı `messages`-də
  - Uğursuz axın: fake generator `PipelineError` atır → `"failed"` +
    səbəbli sistem mesajı
- **Real pipeline sınağı bu fazanın əhatəsində deyil** — real API açarı
  (`GROQ_API_KEY`) tələb edir, əvvəlki spec-də (AI pipeline) olduğu kimi
  istifadəçinin öz mühitinə saxlanılır. Bu fazanın real smoke-u yalnız
  HTTP+thread+disk+broadcast "boru xəttinin" fake generator ilə real
  `uvicorn` üzərində qırılmadığını yoxlayır

## 8. Əhatə xaricində

- Tək-material `GET /chats/{id}/materials/{material_id}` endpoint-i
- Material silinməsi/yenidən emalı (retry) endpoint-i
- Fayl növünün "sehrli bayt" (magic bytes) yoxlaması — yalnız
  uzantı/`kind` uyğunluğuna etibar edilir
- Yenidən başlama zamanı yarımçıq emalların bərpası
- Yüklənmiş faylların uzunmüddətli saxlanma siyasəti (təmizləmə, backup)
