# MasterAI — Dostluq/Sosial Qraf Endpoint-ləri (Dizayn Sənədi)

**Tarix:** 2026-09-02
**Status:** Təsdiqlənib (istifadəçi tərəfindən), implementasiya planına keçilir
**Əhatə dairəsi:** Dost sorğusu göndər/qəbul/rədd/ləğv et, dostluğu poz
(unfriend) HTTP səthi + birbaşa (direct) çat yaratmanın dostluq şərtinə
bağlanması.

## 1. Problem və məqsəd

`FriendshipStore` backend auth fazasında yaradılıb (`pending` sorğu
yaratma, oxuma) — amma qəbul/rədd axını, HTTP səthi və çatla əlaqə
yoxdur. Bu sənəd istifadəçilərin bir-birini necə "dost" edəcəyini və
bunun birbaşa çat yaratmaya necə təsir edəcəyini təsvir edir.

## 2. Mövcud kodda aşkarlanan boşluqlar (düzəldiləcək)

- **`FriendshipStore`-da `threading.Lock`/`RLock` YOXDUR** — reponun
  bütün digər Store-larında olan qorunma (bax `masterai/CLAUDE.md`,
  "Dərs" bölməsi) bu sinifdə əskikdir. Bu fazada əlavə olunur.
- **`UNIQUE(requester_id, addressee_id)` yalnız bir istiqaməti əhatə
  edir** — A→B sorğusu varkən B→A sorğusu maneəsiz yaradıla bilər
  (iki ayrı sətir). Tətbiq səviyyəsində simmetrik yoxlama (`find_between`)
  ilə düzəldilir.
- **Rədd olunmuş/ləğv edilmiş sorğudan sonra yenidən sorğu göndərmək
  mümkün deyil** — `UNIQUE` constraint eyni `(requester_id,
  addressee_id)` cütü üçün yeni `INSERT`-i əbədi bloklayır. `create()`
  `quiz_session_store.py`-dəki 3-hallı naxışla yenidən yazılır (bax
  bölmə 3).

## 3. Store dəyişiklikləri (`friendship_store.py`)

```
create(requester_id, addressee_id) -> dict:
    existing = find_between(requester_id, addressee_id)  # hər iki istiqamətdə axtarır
    if existing is None:
        INSERT yeni sətir (status='pending')
    elif existing.status == 'pending':
        raise DuplicateFriendship  # artıq gözləyən sorğu var (hər iki istiqamətdə)
    elif existing.status == 'accepted':
        raise AlreadyFriends
    else:  # 'declined' | 'cancelled' | 'unfriended' — terminal, yenidən sorğuya icazə
        UPDATE existing sətri: requester_id/addressee_id (YENİ rollarla),
        status='pending', created_at=indi, responded_at=NULL
    return get(id)
```

Bu, `QuizSessionStore.create()`-in "yeni/finished-i əvəz et/active-də
rədd et" məntiqinin birbaşa təkrarıdır (fərq: 2 terminal status əvəzinə
3 — `declined`/`cancelled`/`unfriended`).

Yeni metodlar:
- `find_between(user_a, user_b) -> dict | None` — `WHERE (requester_id=?
  AND addressee_id=?) OR (requester_id=? AND addressee_id=?)`
- `update_status(friendship_id, status) -> None` — `responded_at`-i də
  `status IN ('accepted','declined','cancelled','unfriended')` olanda
  indiki vaxta təyin edir
- `are_friends(user_a, user_b) -> bool` — `find_between(...)?.status ==
  'accepted'`

`__init__`-ə `self._lock = threading.Lock()` (nested public-metod
çağırışı yoxdur — `create()` `find_between`/`get`-i private `_locked`
formalarla çağıracaq ki, `RLock` lazım olmasın, `user_store.py`-nin
əvvəlki fazalardakı naxışına bənzər).

### 3.1. `app.py`-də qeydiyyat

Digər Store-larla eyni naxış: `app.state.friendship_store =
FriendshipStore(os.environ.get("FRIENDSHIPS_DB_PATH", "friendships.db"))`
+ `get_friendship_store()` dependency (testdə `:memory:` ilə override
olunur).

## 4. REST səthi (`server/app.py`) — hamısı `Authorization: Bearer` tələb edir

### `POST /friends/requests`

Body: `addressee_email: str | None`, `addressee_user_id: int | None` —
**dəqiq biri** doldurulmalıdır (`model_validator`, əks halda `422`).

- Ünvanlanan tapılmırsa (email/ID) → `404`
- Özünə sorğu (`addressee.id == user.id`) → `400`
- `FriendshipStore.create()` `DuplicateFriendship`/`AlreadyFriends`
  atarsa → `409`
- Uğurlu: `201`, `FriendshipInfo`

### `GET /friends/requests`

Cari istifadəçiyə aid **pending** sorğular (`list_by_user` + status
filtri) — gələn və gedən eyni siyahıda, client `requester_id ==
mənim_id`-imə görə rolunu ayırd edir.

### `POST /friends/requests/{friendship_id}/accept`

- Sorğu tapılmır → `404`
- Cari istifadəçi `addressee_id` deyil → `403`
- Status `pending` deyil → `409`
- Uğurlu: `update_status(..., 'accepted')`, `200`, `FriendshipInfo`

### `POST /friends/requests/{friendship_id}/decline`

Eyni qapılar (`accept` ilə eyni), `status='declined'`.

### `POST /friends/requests/{friendship_id}/cancel`

- Sorğu tapılmır → `404`
- Cari istifadəçi `requester_id` deyil → `403`
- Status `pending` deyil → `409`
- Uğurlu: `status='cancelled'`, `200`

### `GET /friends`

Cari istifadəçinin **accepted** dostluqları (`list_by_user` + status
filtri).

### `POST /friends/{friendship_id}/unfriend`

- Sorğu tapılmır → `404`
- Cari istifadəçi nə `requester_id`, nə `addressee_id` → `403`
- Status `accepted` deyil → `409`
- Uğurlu: `status='unfriended'`, `200`

## 5. Çat yaratma dəyişikliyi

`POST /chats` (`kind="direct"`) endpoint-inə `FriendshipStore`
asılılığı əlavə olunur. Peer tapıldıqdan sonra:

```
if not friendships.are_friends(user["id"], req.peer_user_id):
    raise HTTPException(403, "Yalnız dostlarla birbaşa çat yaradıla bilər")
```

**Geriyə uyğunluq pozulması (bilərəkdən):** mövcud
`test_chat_endpoints.py::TestCreateDirectChat::test_creates_chat_with_both_members`
indi əvvəlcə dostluq qurmalıdır (sorğu+qəbul) — implementasiya fazasında
yenilənəcək. Qrup çatları (`kind="group"`) və `join` təsirlənmir.

## 6. Pydantic modelləri (`server/models.py`)

```python
class SendFriendRequestRequest(BaseModel):
    addressee_email: str | None = None
    addressee_user_id: int | None = None

    @model_validator(mode="after")
    def _exactly_one(self):
        if (self.addressee_email is None) == (self.addressee_user_id is None):
            raise ValueError("addressee_email VƏ YA addressee_user_id — dəqiq biri")
        return self


class FriendshipInfo(BaseModel):
    id: int
    requester_id: int
    addressee_id: int
    status: str
    created_at: str
    responded_at: str | None
```

## 7. Xəta idarəetməsi

- Bütün `409` hallar (artıq dost/pending/status uyğunsuzluğu) aydın
  Azərbaycan mesajı ilə (`detail`) — client-in fərqli halları
  ayırd etməsi üçün mesaj mətni fərqli olacaq
- `are_friends`/`find_between` istiqamətsiz işləyir — A→B və B→A eyni
  cavabı verir

## 8. Test strategiyası

- `test_friendship_store.py`-ə əlavələr: `find_between` (hər iki
  istiqamətdən tapır), `are_friends`, `update_status`, `create()`-in 3
  halı (yeni/terminal-əvəz/pending-rədd/accepted-rədd)
- `test_friendship_endpoints.py` (yeni): hər endpoint üçün uğur +
  bütün 40x hallar (yuxarıdakı bölmələr), tam axın (sorğu→qəbul→`GET
  /friends`-də görünür), rədd/ləğv/unfriend-dən sonra yenidən sorğu
  mümkünlüyü
- `test_chat_endpoints.py`: `test_creates_chat_with_both_members`
  dostluq qurulması ilə yenilənir; yeni test — dost olmayan iki
  istifadəçi arasında birbaşa çat cəhdi → `403`

## 9. Əhatə xaricində

- İstifadəçi axtarışı/siyahısı (email/ID artıq bilinməlidir — tətbiqin
  gələcək "kontakt idxalı" funksiyası ayrı fazadır)
- Bloklama (block) funksiyası
- Dostluq bildirişləri (push/WebSocket) — hazırkı fazada yalnız REST,
  real-time bildiriş yoxdur (chat mesajlarından fərqli olaraq)
- Qarşılıqlı dost sayı/tövsiyə sistemi
