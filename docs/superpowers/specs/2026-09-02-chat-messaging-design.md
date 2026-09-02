# MasterAI — Əsas Çat: Mesajlaşma + WebSocket (Dizayn Sənədi)

**Tarix:** 2026-09-02
**Status:** Təsdiqlənib (istifadəçi tərəfindən), implementasiya planına keçilir
**Əhatə dairəsi:** Çat yaratma/qoşulma (minimal REST) + real-time mətn
mesajlaşması (WebSocket) + persistence. **AI quiz orkestrasiyası (növbəli
sual axını, timer, xal) bu sənədin əhatəsindən kənardadır** — "Faza B"
kimi ayrıca spec-də dizayn ediləcək, bu fazanın üzərinə qurulacaq.

## 1. Problem və məqsəd

Auth+data modeli (əvvəlki spec) `chats`/`chat_members` cədvəllərini
yaratdı, amma onları işlədən heç bir HTTP/WebSocket səthi yoxdur. Bu
sənəd MasterAI-ın "əsas çat" funksionallığını təsvir edir — istifadəçilər
çat yarada, qoşula, real-time mətn mesajı göndərə bilsin. Bu, AI quiz
axınının (Faza B) üzərinə quracağı canlı kanaldır.

## 2. Arxitektura

```
masterai/server/
  message_store.py         # MessageStore — sqlite3, digər Store-larla eyni naxış
  connection_manager.py       # Proses-daxili WebSocket reyestri (chat_id -> bağlantılar)
  app.py                         # +POST /chats, +GET /chats, +POST /chats/{id}/join,
                                  # +WS /ws/chat/{chat_id}
```

**Proses-daxili məhdudiyyət:** `ConnectionManager` yaddaşdadır (Python
dict) — tək server prosesi fərz edilir (MVP/pilot miqyası). Çoxlu server
instansı ilə horizontal miqyaslanma (Redis pub/sub və s.) bu fazanın
əhatəsindən kənardadır.

## 3. DB sxemi (yeni cədvəl)

```sql
CREATE TABLE messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER NOT NULL,
    sender_id  INTEGER,           -- NULL = AI/sistem mesajı (Faza B üçün yer)
    kind       TEXT NOT NULL,     -- bu fazada: 'text' | 'system'
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
```

`kind` sərbəst TEXT-dir (CHECK məhdudiyyəti yoxdur) — Faza B-də
`quiz_question`/`quiz_result` əlavə olunanda miqrasiya lazım olmayacaq.

**REST əlavələri (mövcud `ChatStore`-u işlədir, yeni cədvəl yaratmır):**
- `POST /chats` `{kind: "group", name}` → yeni qrup çatı, sorğu göndərən
  avtomatik üzv olur (`ChatStore.create` + `add_member`) → 201
- `POST /chats` `{kind: "direct", peer_user_id}` → iki nəfərlik çat,
  sorğu göndərən VƏ `peer_user_id` avtomatik üzv olur → 201.
  `peer_user_id` mövcud olmayan istifadəçidirsə → `404`
- `GET /chats` → cari istifadəçinin çatları (`ChatStore.list_by_user`)
- `POST /chats/{chat_id}/join` → yalnız `kind="group"` çatlar üçün,
  cari istifadəçini üzv əlavə edir (`ChatStore.add_member`, artıq
  idempotentdir) → 200. `direct` çata `join` çağırışı `400` qaytarır —
  "direct" tərkibi sabitdir, kənardan qoşulma mənasızdır

**Qeyd — dəvət mexanizmi sadələşdirilib:** qrupa qoşulmaq üçün hazırda
sadəcə `chat_id`-i bilmək kifayətdir (access control yoxdur, autentifikasiya
kifayətdir). Əsl dəvət linki/icazə sistemi "dostluq/sosial qraf"
alt-sisteminin əhatəsindədir — bura qəsdən sadə saxlanılıb.

## 4. WebSocket protokolu

**Endpoint:** `WS /ws/chat/{chat_id}?token=<JWT>`

Token query parametrində ötürülür (brauzer WebSocket API-si custom
header dəstəkləmir — Flutter web uyğunluğu üçün). **Bilinən tərəf-təsiri:**
uzunömürlü (90 gün) JWT URL-də görünür, server loglarına düşə bilər.
Bu fazada qəbul edilən risk kimi qeyd olunur (dildostu-nun HTTP
`Authorization` başlığı ilə eyni tokeni işlətməsi ilə paralel) — gələcəkdə
qısaömürlü WS-özəl "ticket" tokeni ilə sərtləşdirilə bilər.

**Qoşulma axını:**
1. Server tokeni doğrulayır (`verify_token`) → `user_id`
2. `ChatStore` ilə istifadəçinin bu çatın üzvü olduğu yoxlanılır
3. Etibarsız token və ya üzv olmayan istifadəçi → bağlantı `4401` kodu ilə
   rədd edilir (`accept()`-dən əvvəl)
4. Uğurlu olsa: `accept()` → son 50 mesaj `{"type": "history", "messages": [...]}`
   kimi göndərilir → `ConnectionManager.connect(chat_id, user_id, ws)`

**Mesaj formatları (JSON):**

Client → Server:
```json
{"type": "text", "content": "Salam, hazırsınız?"}
```

Server → bütün qoşulu üzvlərə (broadcast, **göndərən daxil** — server
tək mənbə həqiqətdir, client optimistic-echo etmir, öz mesajını da bu
kanaldan geri alır):
```json
{"type": "message", "id": 42, "chat_id": 1, "sender_id": 3, "kind": "text",
 "content": "Salam, hazırsınız?", "created_at": "2026-09-02T18:00:00+00:00"}
```

Naməlum/yanlış formatlı client mesajı → yalnız göndərənə:
```json
{"type": "error", "detail": "mesaj formatı düzgün deyil"}
```
(bağlantı kəsilmir, digər üzvlərə təsir etmir)

## 5. Xəta idarəetməsi

- Etibarsız/vaxtı keçmiş token → qoşulma rədd (`4401`), heç bir mesaj
  emal olunmur
- Çat üzvü olmayan istifadəçi → qoşulma rədd (`4403`)
- Naməlum `chat_id` (mövcud olmayan çat) → qoşulma rədd (`4404`)
- Broadcast zamanı bir alıcının bağlantısı artıq qopubsa (stale
  connection) → o bağlantı sakitcə `ConnectionManager`-dən silinir,
  qalan alıcılara göndərmə davam edir (bir qırıq bağlantı hamısını
  batırmır)
- Server prosesi yenidən başlayanda **bütün aktiv WebSocket bağlantıları
  itir** (yaddaş-daxili reyestr) — client-lər öz tərəfində reconnect
  məntiqi tətbiq etməlidir (bu fazanın əhatəsində deyil, Flutter
  tərəfinin işidir)

## 6. Test strategiyası

- `test_message_store.py` — create/list_by_chat (sıra, pagination əsas
  hallar)
- `test_connection_manager.py` — connect/disconnect/broadcast (mock
  WebSocket obyektləri ilə, real şəbəkə yoxdur), stale bağlantının
  broadcast-ı batırmadığı
- `test_chat_endpoints.py` — `POST /chats`, `GET /chats`,
  `POST /chats/{id}/join` (`httpx.TestClient`, mövcud auth naxışı)
- `test_chat_websocket.py` — `TestClient.websocket_connect()` ilə:
  - etibarsız token → rədd
  - üzv olmayan istifadəçi → rədd
  - qoşulanda tarixçə (`history`) gəlir
  - mətn mesajı göndərilir → DB-yə yazılır VƏ bütün qoşulu üzvlərə
    yayımlanır (2+ test client eyni çata qoşulub yoxlanılır)
  - yanlış formatlı mesaj → `error` frame, bağlantı kəsilmir
  - bir client ayrılanda digərləri normal davam edir

## 7. Əhatə xaricində (Faza B və sonrası)

- AI quiz orkestrasiyası (növbəli sual göndərmə, timer, erkən keçid,
  `chat_quiz_sessions` cədvəli) — ayrı spec
- `quiz_question`/`quiz_result` mesaj növləri (sxem hazırdır, məntiq yoxdur)
- Real dəvət linki/icazə sistemi qrup çatları üçün
- Horizontal miqyaslanma (çoxlu server prosesi, Redis pub/sub)
- Mesaj redaktəsi/silinməsi, oxunma statusu, tipinq göstəricisi
