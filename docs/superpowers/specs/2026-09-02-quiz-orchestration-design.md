# MasterAI — AI Quiz Orkestrasiyası (Faza B) (Dizayn Sənədi)

**Tarix:** 2026-09-02
**Status:** Təsdiqlənib (istifadəçi tərəfindən), implementasiya planına keçilir
**Əhatə dairəsi:** Hazır materialın (`materials.status="ready"`) sualları
üzərində çatda növbəli AI quiz axını — başlatma, sual göndərmə, cavab
qəbulu, avtomatik növbə keçidi (timeout/hamı cavablayıb), yekun xülasə.
**Faza A (əsas çat) üzərinə qurulur** — mövcud `messages`,
`ConnectionManager`, `WS /ws/chat/{chat_id}` genişləndirilir, yeni
paralel infrastruktur qurulmur.

## 1. Problem və məqsəd

Faza A çatda mətn mesajlaşmasını verdi. Bu sənəd MasterAI-ın əsas dəyər
təklifini — "material yüklə, dostlarla birgə canlı quiz həll et" —
mövcud çat kanalının üzərinə qurur. AI burada sual "göndərən" tərəf
kimi iştirak edir (`sender_id=NULL` mesajlar, Faza A-nın `kind` sahəsi
bunun üçün əvvəlcədən hazırlanmışdı).

## 2. Arxitektura

```
masterai/server/
  quiz_session_store.py   # QuizSessionStore — chat_quiz_sessions cədvəli
  quiz_runner.py             # start_quiz, record_answer, advance_question, check_timeout
  quiz_attempt_store.py         # +list_by_question(question_id) (Faza 1 Store-una əlavə)
  chat_store.py                    # +list_member_ids(chat_id) (Faza 1 Store-una əlavə)
  app.py                              # +POST /chats/{id}/quiz/start, WS-ə "answer" mesaj tipi
```

**Fon tapşırığı (timeout):** hər sual göndəriləndə
`asyncio.create_task(check_timeout(...))` planlaşdırılır. Tapşırıq
obyekti `app.state.active_quiz_timeouts: dict[chat_id, asyncio.Task]`-da
saxlanılır (Python-un zəif referanslı task-ı vaxtından əvvəl
"çöp yığmaması" üçün — sadəcə arayışsız `create_task` real production-da
riskli praktikadır).

**Yarış vəziyyəti (race condition) qeydi — niyə kilid lazım deyil:**
`record_answer`-in "cavabı yaz + hamı cavablayıbmı yoxla" bölməsi
tamamilə sinxron `sqlite3` çağırışlarından ibarətdir, arada `await`
yoxdur. Python asyncio-nun əməkdaşlıq əsaslı planlaşdırıcısı bir task-ı
yalnız `await` nöqtəsində dəyişdirir — deməli bu bölmə təbii şəkildə
atomikdir, əlavə `asyncio.Lock` lazım deyil. **Xəbərdarlıq:** Store
qatı gələcəkdə async DB driverinə keçsə (məs. `aiosqlite`), bu
invariantı qorumaq üçün açıq kilid əlavə edilməlidir — sadəcə
`await`-ə çevirmək bu bölməni yarış vəziyyətinə açıq edər.

## 3. DB sxemi (yeni cədvəl)

```sql
CREATE TABLE chat_quiz_sessions (
    chat_id                     INTEGER PRIMARY KEY,
    material_id                  INTEGER NOT NULL,
    question_ids                  TEXT NOT NULL,   -- JSON massiv, sıra ilə
    current_index                   INTEGER NOT NULL,
    current_question_started_at       TEXT NOT NULL,
    status                              TEXT NOT NULL  -- 'active' | 'finished'
);
```

Bir çatda eyni anda yalnız **bir** aktiv sessiya ola bilər (`chat_id`
PRIMARY KEY — həm də eyni çatda ardıcıl quiz turlarının tarixçəsini
saxlamır, yalnız SONUNCU turu təmsil edir). `QuizSessionStore.create`
məntiqi:
- Mövcud sətir yoxdursa → adi `INSERT`
- Mövcud sətrin statusu `"finished"`-dirsə → `UPDATE` (yeni tur
  köhnəni **əvəz edir**, yeni `material_id`/`question_ids` ilə)
- Mövcud sətrin statusu `"active"`-dirsə → `QuizAlreadyActive` atılır →
  endpoint `409`

Nəticə: eyni çatda materialları ardıcıl (bir bitəndən sonra o biri)
quiz kimi işə salmaq mümkündür, amma paralel (eyni anda iki aktiv)
mümkün deyil.

## 4. Axın və protokol

### REST: `POST /chats/{chat_id}/quiz/start {material_id}`

- Yalnız `materials.uploaded_by == cari istifadəçi` → əks halda `403`
- `material.chat_id != chat_id` (path) → `400` (material bu çata aid deyil)
- `material.status != "ready"` → `400`
- Bu çatda aktiv sessiya var → `409`
- Materialın sualı yoxdur (`QuestionStore.list_by_material` boş) → `400`
- Uğurlu: sessiya yaradılır, 1-ci sual `quiz_question` mesajı kimi
  yazılıb broadcast olunur, timeout task planlaşdırılır → `201`

### WebSocket mesaj növləri (mövcud `/ws/chat/{chat_id}`-ə əlavə)

**Server → client, sual açılanda (`quiz_question`):**
```json
{"type": "quiz_question", "question_id": 12, "question": "...",
 "options": ["A", "B", "C", "D", "E"], "message_id": 55}
```
`correct_index`/`explanation` **BURADA YOXDUR** — nə broadcast payload-da,
nə də DB-də saxlanılan mesaj `content`-ində (bax bölmə 5).

**Client → server, cavab (mövcud "text" tipinin yanında yeni tip):**
```json
{"type": "answer", "question_id": 12, "chosen_index": 2}
```

**Server → client, sual bağlananda (`quiz_result`, hamıya):**
```json
{"type": "quiz_result", "question_id": 12, "correct_index": 2,
 "explanation": "...", "answers": [{"user_id": 3, "chosen_index": 2, "is_correct": true}, ...],
 "message_id": 56}
```

**Server → client, quiz bitəndə (`quiz_finished`, hamıya):**
```json
{"type": "quiz_finished", "total_questions": 5,
 "scores": {"3": 4, "7": 2}, "message_id": 60}
```

**Növbə keçidi iki yoldan biri ilə baş verir:**
1. Çatın BÜTÜN üzvləri (`ChatStore.list_member_ids`) hazırkı suala
   cavab verib — dərhal keçid
2. `DEFAULT_QUESTION_TIMEOUT_SECONDS = 45` (tənzimlənə bilən) saniyə
   keçib — kim cavablamayıbsa, cavabsız sayılır, keçid baş verir

### Xüsusi hallar (cavab qəbulu)

- Cavab hazırkı aktiv sualdan fərqli `question_id`-yə aiddir (köhnə
  sual üçün gecikmiş cavab) → `NotCurrentQuestion` → yalnız göndərənə
  `error` frame
- İstifadəçi bu sualı artıq cavablayıb → `AlreadyAnswered` → yalnız
  göndərənə `error` frame
- Bu çatda aktiv sessiya yoxdur → `QuizError` → yalnız göndərənə
  `error` frame

## 5. Xəta idarəetməsi və təhlükəsizlik

- **Cavab sızması qadağandır:** `quiz_question` mesajının həm broadcast
  payload-ı, həm DB-də saxlanan `content`-i yalnız `question_id`,
  `question`, `options` daşıyır — `correct_index`/`explanation` yalnız
  `quiz_result`-da (sual artıq bağlananda) göndərilir
- Timeout task-ı işə düşəndə sessiyanın hələ də həmin sualda olduğunu
  yoxlayır (`current_index` müqayisəsi) — artıq keçilmişsə sakitcə
  heç nə etmir (idempotent no-op, bax bölmə 2)
- Server prosesi yenidən başlayanda **planlaşdırılmış timeout task-ları
  itir** (yaddaş-daxili) — DB-dəki sessiya statusu qalır, amma heç kim
  onu avtomatik irəli aparmır. Bu fazanın bilinən məhdudiyyətidir
  (production-da "stuck" sessiyaları aşkarlayan ayrı bir mexanizm
  lazım olacaq — əhatə xaricində)

## 6. Test strategiyası

- `test_quiz_session_store.py` — create/get/advance (son sualdan sonra
  `finished`), `QuizAlreadyActive`
- `test_quiz_attempt_store.py`-ə əlavə — `list_by_question`
- `test_chat_store.py`-ə əlavə — `list_member_ids`
- `test_quiz_runner.py` — `start_quiz`, `record_answer` (uğurlu, təkrar
  cavab, köhnə sual), `advance_question` (aralıq sual → növbəti sual,
  son sual → `quiz_finished`) — fake `connection_manager`/`message_store`
  ilə, DB-lər real (`:memory:`)
- `test_quiz_runner_timeout.py` — real, qısa (`0.2` saniyə) timeout
  dəyəri ilə: cavabsız qalanda avtomatik keçid; hamı cavablayanda
  timeout-dan ƏVVƏL keçidin baş verdiyi (timeout sonra sakitcə no-op
  etdiyi) — dildostu-nun `test_expired_token_rejected` naxışı
- `test_quiz_endpoints.py` — `POST .../quiz/start` icazə/status/əhatə
  yoxlamaları (403/400/409)
- `test_quiz_websocket.py` — real WS axını: sual gəlir → cavab
  göndərilir → (2 üzvdən hamısı cavablayanda) `quiz_result` dərhal gəlir
  → (materialın son sualı deyilsə) növbəti `quiz_question` gəlir

## 7. Əhatə xaricində

- Server restart-dan sonra yarımçıq sessiyaların bərpası
- Vaxt göstəricisi (client-ə "N saniyə qaldı" göndərmə) — client öz
  tərəfində sadə geri sayım apara bilər, server dəqiq qalan vaxtı
  broadcast etmir
- Çətinlik səviyyəsinə görə sual seçimi/sıralaması
- Adaptiv quiz (istifadəçi səviyyəsinə görə fərqli suallar)
