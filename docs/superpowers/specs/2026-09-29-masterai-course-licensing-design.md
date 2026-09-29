# Kurs lisenziyası, sahib paneli və ingilis dili profili

**Tarix:** 2026-09-29
**Status:** dizayn təsdiqlənib (bölmə-bölmə), icra planı gözləyir

## Kontekst

İngilis dili kursu (bir müəllim + tələbə qrupu) MasterAI-ni **1 ay pulsuz**
sınayacaq, uğurlu olarsa ödənişli davam edəcək. İstifadəçinin tələbləri:

1. Sayt kurs üçün 1 ay pulsuz olsun, ödənişdən sonra davam etsin.
2. Yollar ayrılanda kurs saytdan **pulsuz istifadə edə bilməsin** — bunu
   idarə etmək üçün panel.
3. «Saytın təhlükəsizliyini tam təmin etməliyik ki, gələcəkdə tələbələr
   tərəfindən sistemə hack müdaxilələri olmasın.»
4. Suallar ingilis dili dərsinə uyğun olsun (tələbə səviyyəsi maksimum B1).

Hazırda sistemdə **kurs (tenant) anlayışı yoxdur**: qeydiyyat hamıya
açıqdır, bütün istifadəçilər bir hovuzdadır, generasiya promptu dövlət
qulluğu imtahanına sabit bağlıdır (`pipeline/generation.py:20`).

## Qəbul edilmiş qərarlar

| Mövzu | Qərar |
|---|---|
| Müddət bitəndə | **Tam bağlanma**: nə müəllim, nə tələbə girə bilir, yalnız «abunə bitib, sahiblə əlaqə saxlayın» ekranı. **Data silinmir**, ödənişdən sonra dərhal açılır |
| Xəbərdarlıq | Bitməyə **5 gün** qalmış: müəllimə saytda banner, sahibə Telegram (n8n) |
| Qiymət modeli | Sabit qiymət + **tələbə yeri limiti**. Müəllim limiti yoxdur, amma panelda müəllim sayı görünür |
| Arxitektura | İstifadəçi **bir kursa** aiddir (`users.course_id`) + mərkəzi lisenziya qapısı |
| Başlamış canlı sessiya | Lisenziya bitsə belə **sonuna qədər gedir** |
| Müəllim dəvəti | **Yalnız platforma sahibi** yaradır |
| Yükləmə limiti | Gündə tələbə **5**, müəllim **30** material/bank |
| Sual dili | Sual və variantlar ingiliscə, izah azərbaycanca, səviyyə A2–B1 |
| Reading sualları | **Yalnız ev tapşırığında** (mətn tələbənin qarşısında olanda) |
| Ödəniş | Panelda əl ilə qeyd olunur (ödəniş sistemi inteqrasiyası yoxdur) |

## 1. Data modeli

### Yeni cədvəl: `courses` (users.db daxilində)

| Sütun | Məna |
|---|---|
| `id`, `name`, `created_at` | |
| `profile` | `exam_prep` \| `english` |
| `status` | `owner` \| `trial` \| `active` \| `suspended` |
| `trial_ends_at` | sınaq sonu (UTC ISO) |
| `paid_until` | ödənilmiş dövrün sonu (UTC ISO, boş ola bilər) |
| `seat_limit` | aktiv tələbə limiti |
| `join_code` | tələbə qeydiyyat kodu |
| `upload_limit_student`, `upload_limit_teacher` | gündəlik limit (defolt 5 / 30) |

**«Bitib» vəziyyəti saxlanılmır, tarixdən hesablanır:**

- `owner` → həmişə açıq
- `trial` → `now < trial_ends_at` olduqca açıq
- `active` → `now < paid_until` olduqca açıq
- `suspended` → bağlı

Səbəb: `expired` statusunu yazan cron işi olsaydı, o iş dayandığı gün
kurslar **səssizcə pulsuz** qalardı. Tarixdən hesablama heç vaxt
«unudulmur».

### `users` cədvəlinə əlavələr

- `course_id` — istifadəçinin kursu
- `is_active` (defolt 1) — 0 olanda giriş bağlanır və tələbə yeri boşalır
- `is_platform_owner` (defolt 0) — ilk dəfə VPS-də əl ilə təyin olunur
  (`is_admin` kimi); API ilə bu bayrağı dəyişən endpoint **yoxdur**

`is_teacher` kurs daxilində məna daşıyır. `is_admin`-in «müəllim et»
hüququ yalnız **öz kursunun** istifadəçilərinə şamil olunur.

### Obyektlərə `course_id`

Store-lar **ayrı SQLite fayllarındadır** (`chats.db`, `question_sets.db`,
`live_sessions.db`, ...) — fayllar arası JOIN mümkün deyil. Ona görə
yüksək səviyyəli obyektlər yaradılanda yaradanın `course_id`-si onlara
yazılır: `chats`, `question_sets`, `live_sessions`. Ev tapşırığı kursunu
çatdan alır.

### Kiçik cədvəllər

- `teacher_invites` — `token_hash` (SHA-256; tokenin özü saxlanmır),
  `course_id`, `expires_at` (7 gün), `used_at`, `used_by`
- `owner_audit_log` — `at`, `owner_id`, `course_id`, `action`, `details`

### Miqrasiya

Mövcud qayda ilə (`ALTER TABLE` + `OperationalError` tutulur). Kurs #1
yaradılır: `status=owner`, `profile=exam_prep`, müddətsiz. **Bütün
mövcud istifadəçilər və obyektlər** kurs #1-ə yazılır. Nəticə: Amil və
digər mövcud istifadəçilər üçün **heç nə dəyişmir** — bu, testlə
sübut olunur.

## 2. Lisenziya qapısı

**Tək keçid nöqtəsi:** `get_current_user` (`server/app.py:314`). Bütün
HTTP endpoint-lər onun üzərindən keçir; `get_current_teacher` ondan
asılıdır. Yoxlama sırası:

1. Token etibarlıdır (mövcud)
2. `is_active = 1`, deyilsə → 401 (token artıq işləmir)
3. Kurs açıqdır (yuxarıdakı qayda), deyilsə → **402** + «abunə bitib»
4. Platforma sahibi 2–3-dən azaddır

Lisenziya **hər sorğuda bazadan** oxunur, JWT-yə yazılmır: dayandırma
dərhal təsir edir, 90 günlük token problem deyil.

**WebSocket-lər** (`/ws/chat/{id}`, `/ws/live/sessions/{id}/host`,
`/ws/live/sessions/{id}/play`) `verify_token`-i birbaşa çağırır — qapı
onlara ayrıca qoşulur. Rədd: `accept()` + xəta mesajı + `close(4402)`
(accept-siz close brauzerdə 1006 görünür və klient sonsuz yenidən
qoşulur — bu, `app.py:1331`-də sənədləşib). `4402`
`web/assets/js/socket.js`-dəki `FATAL_CLOSE_CODES`-a əlavə olunur.

- **Çat WS**: hər mesajda bazadan yoxlanır. (İlk variantda 60 saniyəlik keş
  nəzərdə tutulmuşdu; icrada ləğv edildi: bir PK sorğusudur, keş isə
  dayandırmanı 60 saniyə gecikdirərdi.)
- **Canlı sessiya**: qapı **yeni sessiya yaradılanda** yoxlanır. Lisenziya
  bitməzdən əvvəl başlamış sessiyaya qoşulma, yenidən qoşulma və həmin
  sessiyanın HTTP oxu endpoint-ləri sessiya bitənə qədər icazəlidir
  (maksimum 10 dəqiqəlik vaxt büdcəsi ilə məhdud). Sessiya bitəndən
  sonra hər şey bağlanır

**Giriş (`/auth/login`):** kurs yalnız **şifrə doğru olduqdan sonra**
yoxlanır — əks halda «bu e-poçt bağlı kursdadır» məlumatı sızar.
Bağlı kursda cavab 402, frontend «abunə bitib» ekranını göstərir.

**Xəbərdarlıq:** `GET /me/course` → `{status, days_left}`. Yalnız
müəllimə, `days_left ≤ 5` olanda banner. `/admin/stats` (n8n) bitməyə
yaxın kursların siyahısını qaytarır → Telegram.

## 3. Sahib paneli (`sahib.html`)

Yalnız `is_platform_owner`. Naviqasiya linki frontend-də gizlədilir, amma
qoruma **serverdədir**: `/owner/*` endpoint-ləri `get_platform_owner`
asılılığı ilə qorunur, `test_endpoint_guards.py` markerlərinə əlavə
olunur.

**Kurs siyahısı:** ad, profil, hesablanmış status + qalan gün, aktiv
tələbə / limit, müəllim sayı, son 7 gün (sessiya, bank, cavab sayı),
son aktivlik. Aktivlik **mövcud cədvəllərdən sayılır** — yeni izləmə
kodu yazılmır.

**Əməliyyatlar:** kurs yarat (ad, profil, sınaq günü defolt 30, tələbə
limiti) · ödənildi (+N ay, `active`) · dayandır / bərpa et · limiti
dəyiş · tələbə kodunu yenilə · müəllim dəvəti yarat (birdəfəlik, 7
gün). Hər əməliyyat `owner_audit_log`-a yazılır — ödəniş mübahisəsində
tarix mənbədən görünür.

**nginx:** `/owner/` və `/me/` `deploy/nginx-masterai.conf`-dakı API yol
siyahısına əlavə olunmalıdır, əks halda nginx statik fayl axtarıb 404
qaytarır. `test_nginx_routes.py` bunu tutur.

## 4. Qapalı qeydiyyat və təhlükəsizlik

Kodda tapılan real boşluqlar və həlləri:

| # | Boşluq | Yer | Həll |
|---|---|---|---|
| 1 | Qeydiyyat hamıya açıq | `app.py:362` | Yalnız kurs kodu ilə; kod kursu müəyyən edir; tələbə limiti **burada** yoxlanır (yoxlama + yazma bir tranzaksiyada, iki eyni-anlı qeydiyyat limiti aşa bilməz). Kod yoxlamasına `RateLimiter` (IP üzrə dəqiqədə 5). Müəllim yalnız dəvət linki ilə |
| 2 | Girişdə cəhd limiti yox | `app.py:375` | **E-poçt + IP** üzrə 15 dəqiqədə 10 səhv cəhd → müvəqqəti blok. Yalnız e-poçt üzrə olsaydı, tələbə müəllimin e-poçtuna qəsdən səhv şifrə göndərib **müəllimi bloklaya** bilərdi. nginx `X-Real-IP` ötürür |
| 3 | Dostluq sorğusu e-poçtları üzə çıxarır | `app.py:466` | Yalnız öz kursunda; başqa kursun istifadəçisi naməlum e-poçtla **eyni** «tapılmadı» cavabını alır |
| 4 | Ev tapşırığında bankın sahibi yoxlanmır | `app.py:1629` | Bank eyni kursda olmalıdır |
| 5 | Tələbə limitsiz material yükləyir (AI xərci) | `app.py:976`, `app.py:1084` | Gündəlik limit (Bakı vaxtı ilə təqvim günü), mövcud `materials`/`question_sets` cədvəllərindən sayılır |

**Kurs sərhədi hər yerdə.** Başqa kursun obyekti **404** qaytarır (403
yox — 403 «var, amma sənin deyil» məlumatını verir). Hər ID qəbul edən
endpoint üçün avtomatik test: kurs A istifadəçisi kurs B obyektinin
ID-si ilə → 404. Yeni endpoint bu testə düşməsə, yoxlama testi qırmızı
olur (`test_endpoint_guards.py` nümunəsi ilə).

**Saxlanılanlar:** bcrypt, eyni giriş xətası mesajı, `JWT_SECRET` ≥ 32
simvol, 20 MB fayl limiti, istifadəçi mətni yalnız `textContent`.

**Bilərəkdən edilməyənlər:** 2FA, CAPTCHA (30 nəfərlik qrupa sürtünmə
faydadan çoxdur), token müddətini qısaltmaq (hər sorğuda bazadan
yoxlanır, lazım deyil).

## 5. İngilis dili profili

- Generasiya tək nöqtədən keçir (`generate_for_chunks`). `SYSTEM_PROMPT`
  profilə görə seçilir; `exam_prep` mətni **bir hərf də dəyişmir**.
- Profil bank yaradılanda kursdan götürülür və **bankda saxlanılır**.
- `english`: sual və variantlar ingiliscə, izah azərbaycanca, A2–B1,
  qısa cümlələr. 5 variant qalır (`models.py:19` sxemi, A–E rəngləri).
- **Canlı sessiya / çat bankı (`practice`):** lüğət (məna, sinonim,
  kontekstdə söz), qrammatika (boşluq doldurma), işlənmə (hansı cümlə
  düzgündür). Mətnin məzmununu xatırlamağa əsaslanan sual qadağandır —
  tələbənin qarşısında mətn yoxdur.
- **Reading bankı (`reading`):** yalnız `english` profilində, yalnız
  müəllim yaradır. Mənbə mətn bankda saxlanılır (`passage`, uzunluq
  limiti ilə). Ev tapşırığı ekranı mətni sualların üstündə göstərir.
  Canlı sessiya `reading` bankını qəbul etmir (400).

**Keyfiyyət yoxlamaları (`pipeline/quality.py`):**

| Yoxlama | `english` |
|---|---|
| Təkrar variant/sual, uzun variant ipucu, mövqe meyli, zəif izah | olduğu kimi |
| Materiala istinad | ingiliscə ifadələr əlavə olunur («according to the text», «in the passage», ...); `reading` bankında söndürülür |
| E-qanun metadata, qanun düzəlişi | söndürülür |

**Keyfiyyət sübutu:** uydurma data yox. Müəllimin **real** 2–3 mövzu
materialından bank yaradılır, 30 sualı müəllim qiymətləndirir
(doğru/səhv, səviyyəyə uyğun/çətin). Qəbuledilməzdirsə promptu
düzəldirik, pilotu yox.

## Pilotdan əvvəl lazım olanlar (texniki deyil)

- **Baseline (5–7 gün, sistem işə düşməzdən ƏVVƏL):** müəllim bir
  mövzuya test hazırlamağa nə qədər vaxt sərf edir; ev tapşırığının
  icra faizi. Sonradan geri qaytarmaq mümkün deyil.
- Qrupdakı tələbə sayı → ilkin `seat_limit`.
- Müəllimin real dərs materialı (keyfiyyət yoxlaması üçün).
- n8n connector-unun bu mühitdə avtorizasiyası (Telegram bildirişi üçün).

## Faza bölgüsü (ətraflı plan ayrıca)

| Faza | Məzmun | Hazırdır, əgər |
|---|---|---|
| 1 | Data modeli + miqrasiya | mövcud bütün testlər yaşıl; köhnə baza miqrasiyadan sonra eyni işləyir |
| 2 | Lisenziya qapısı (HTTP, WS, giriş) + bağlı ekran + banner | bitmiş/dayandırılmış kurs hər girişdə bağlıdır, sahib və `owner` kursu açıqdır |
| 3 | Qapalı qeydiyyat + müəllim dəvəti + yer limiti | kodsuz qeydiyyat mümkün deyil; limit eyni-anlı sorğularda aşılmır |
| 4 | Kurs sərhədi (bütün endpoint-lər) + dostluq + ev tapşırığı | çarpaz-kurs testi hər ID endpoint-i üçün 404 |
| 5 | Giriş limiti + gündəlik yükləmə limiti | limitlər testlə sübut |
| 6 | Sahib paneli (API + `sahib.html` + jurnal + nginx) | brauzerdə real klik yoxlaması |
| 7 | İngilis profili + reading ev tapşırığı | müəllimin 30 sual qiymətləndirməsi |
| 8 | n8n → Telegram bitmə xəbərdarlığı | test bildirişi Telegram-a çatır |
| 9 | Hücum yoxlaması + deploy + kursun yaradılması | 5 boşluğun hər biri real sorğu ilə bağlı olduğu göstərilir |

Deploy: ehtiyat nüsxə (`cp`, `*` işlətmədən), istifadəçi ilə razılaşdırılmış
vaxtda, `VPS_MAINTENANCE.md` qaydaları ilə.
