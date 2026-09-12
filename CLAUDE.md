# MasterAI — operativ təlimat

Dövlət qulluğu və magistratura imtahanlarına hazırlaşan tələbələr üçün: dərs
materialını (sayt linki, PDF, şəkil) yükləyir → AI ondan MCQ test sualları
çıxarır → şəxsi/qrup çatında dostlarla birgə canlı "quiz" kimi həll edilir.

**Status: canlı və real istifadəyə hazır.** «Qrup çatı = sinif» dəyişikliyi 2026-09-12-də deploy olundu (PIN axını silindi, qoşulma dəvət kodu + müəllim təsdiqi ilədir). `https://masterai.prdostu.com`
— DigitalOcean VPS-də (HTTPS, systemd, nginx). Backend + statik sayt, hər
ikisi deploy olunub.

**Test dəsti: 1190 pytest + 183 Node testi** (`masterai/` daxilində vahid
run: `.venv/bin/python -m pytest -q`, JS üçün `node --test web/tests/*.test.js`).
Rəqəm 2026-09-12-də yoxlanılıb — bu sətir köhnələndə YENİLƏ, köhnə rəqəm
sənədə etibarı azaldır (əvvəl burada aylarla "263 test" yazılı qalmışdı).

Uc-uca real axın təsdiqlənib: qeydiyyat → qrup çatı → mesajlaşma (WS) →
material yükləmə → AI sual generasiyası → quiz həlli → xallandırma.
Flutter app (`app/`) ARXİVDƏDİR — yerini statik sayt tutub (bax
"Veb-first keçidi"). Brainstorming skill-i ilə alt-sistemlərə bölünür,
hər biri öz spec-i ilə (`docs/superpowers/specs/`).

## Arxitektura

`dildostu/` layihəsinin sınanmış naxışı əsas götürülür (Flutter app + FastAPI
backend, `prdostu.com` alt-domenə DigitalOcean deploy, provider fallback
zənciri). `pipeline/` və `server/` eyni `masterai/` kök venv-ini paylaşır
(bax `requirements.txt`, `.venv/`) — `server/` birbaşa `pipeline/`-i idxal edir.

| Alt-sistem | Nədir | Vəziyyət |
|---|---|---|
| AI sual generasiya pipeline-ı (`pipeline/`) | Material ingestion (sayt/PDF/şəkil) + LangChain LCEL + MCQ çıxarılması | ✅ Tamamlandı (57 test) |
| Backend skeleti: Auth + Data modeli (`server/`) | Email+şifrə auth (bcrypt+JWT), 6 cədvəllik DB sxemi, minimal FastAPI | ✅ Tamamlandı (63 test) |
| Əsas çat: mesajlaşma+WebSocket | `messages` cədvəli, `POST/GET /chats`, `WS /ws/chat/{id}` (real-time mətn, broadcast) | ✅ Tamamlandı (29 test) |
| AI Quiz Orkestrasiyası (Faza B) | Növbəli sual axını (`chat_quiz_sessions`), 45san timeout+erkən keçid, `POST /quiz/start`, WS "answer" tipi, xal | ✅ Tamamlandı (34 test) |
| Dostluq/sosial qraf endpoint-ləri | `POST/GET /friends/requests`, accept/decline/cancel, `GET /friends`, unfriend. `POST /chats` (direct) dostluq şərtinə bağlıdır | ✅ Tamamlandı (45 test) |
| Material yükləmə endpoint-i | `POST/GET /chats/{id}/materials`, `asyncio.to_thread` ilə fon emalı (pipeline→sual+sistem mesajı) | ✅ Tamamlandı (21 test) |
| ~~Flutter app (`app/`)~~ | **ARXİV — əvəzlənib** (2026-09-09). Release imzalama açarı yoxdur, Play Store-a dərc olunmayıb → real tələbəyə çatmaq yolu YOX idi. Kod silinməyib | 🗄️ Arxiv, bax `app/README.md` |
| **Veb sayt (`web/`)** | Statik HTML+CSS+vanilla JS, build addımı YOXDUR. Bütün 18 səhifə: açılış, auth, çat+quiz, ev tapşırıqları, tarixçə, nişanlar, müəllim konsolu, canlı sessiya (çatdan), hüquqi səhifələr | ✅ Kod hazır, real backend-lə uc-uca sınaq gözlənilir |
| n8n/MCP admin avtomatlaşdırması | Uğursuz material→Telegram bildirişi VƏ gündəlik statistika — HƏR İKİSİ aktiv, n8n.prdostu.com-da | ✅ Tamamlandı (14 test + 2 aktiv real workflow) |
| Deploy | DigitalOcean (`<SERVER_IP>`, dildostu/masternr1 ilə eyni VPS), `https://masterai.prdostu.com`, systemd+nginx+certbot HTTPS | ✅ Tamamlandı — canlı, real `curl`+n8n icrası ilə təsdiqlənib |
| Canlı Sinif Sessiyası (Kahoot-tərzi, Faza 1 — Master NR 1 pilotu üçün) | Müəllim veb host konsolu + tələbə qoşulması. **PIN axını 2026-09-11-də silindi** — sessiya qrup çatına bağlıdır (bax «Qrup çatı = sinif»), `docs/superpowers/specs/2026-09-07-masterai-live-classroom-design.md`, `.planning/2026-09-07-masterai-live-classroom/` | ✅ Tam uc-uca REAL test edilib (host+tələbə, real AI sualları, real PIN, sessiya hesabatı) — bax aşağı "Canlı Sinif Sessiyası" bölməsi |
| Ev Təkrarı Rejimi (Faza 2 — asinxron fərdi məşq) | Müəllim tapşırıq təyin edir (veb+mobil, `is_teacher` bayrağı) → tələbə "Tapşırıqlarım"da öz sürəti ilə həll edir → müəllim hesabatda görür, `docs/superpowers/specs/2026-09-07-masterai-homework-mode-design.md`, `.planning/2026-09-07-masterai-homework-mode/` | ✅ Tam uc-uca REAL test edilib (təyin→görmə→həll→hesabat) — bax aşağı "Ev Təkrarı Rejimi" bölməsi |
| Fərdi tələbə tarixçəsi (Faza 3 — canlı sessiya + ev tapşırığı birləşmiş tarixçə) | Tələbə "Mənim tarixçəm"də öz keçmiş nəticələrinə baxır, müəllim istənilən tələbəni seçib eynisini görür, `.planning/2026-09-07-masterai-student-history/` | ✅ Tam uc-uca REAL test edilib — bax aşağı "Fərdi tələbə tarixçəsi" bölməsi |
| Çox-müəllimli idarəetmə (Faza 4 — `is_admin` rolu) | Admin (ayrıca `is_admin` bayrağı) tətbiq daxilindən e-poçtla başqa istifadəçini müəllim edir/çıxarır, hazırkı müəllimlərin siyahısını görür — VPS-də əl ilə skript artıq lazım deyil, `.planning/2026-09-07-masterai-multi-teacher-management/` | ✅ Tam uc-uca REAL test edilib — bax aşağı "Çox-müəllimli idarəetmə" bölməsi |
| Sual redaktə/təsdiq ekranı (Faza 5 — mövcud sualları düzəlt/sil) | Müəllim veb host konsolunda hər sual bankının suallarını görüb mətn/variant/düzgün cavab/izahı redaktə edir və ya silir (əlavə etmə/məcburi təsdiq bu fazaya daxil deyil), `.planning/2026-09-07-masterai-question-edit/` | ✅ Tam uc-uca REAL test edilib — bax aşağı "Sual redaktə/təsdiq ekranı" bölməsi |
| Vizual dizayn yenilənməsi | `google_fonts` (Nunito+Inter), `ThemeExtension<AppSubjectColors>` (6 fənn aksent rəngi), işıq/tünd rejim, canlı sessiya/həll ekranlarının "enerjili" gücləndirilməsi, `docs/superpowers/specs/2026-09-08-masterai-visual-design-refresh.md`, `.planning/2026-09-08-masterai-visual-design/` | ✅ Phase 1-4 REAL test edilib. Phase 5 (animasiya) kodca hazır, son real təsdiqi gözlənilir |
| Nailiyyət nişanları + Liderlik lövhəsi (Faza 6) | 5 tənbəl-hesablanan nişan (`GET /badges/me`) + hər qrup çatı üçün ev tapşırığı xallarına görə liderlik lövhəsi (`GET /chats/{id}/leaderboard`), `docs/superpowers/specs/2026-09-08-masterai-badges-leaderboard-design.md`, `.planning/2026-09-08-masterai-badges-leaderboard/` | ✅ Tam uc-uca REAL test edilib — bax aşağı "Nailiyyət nişanları + Liderlik lövhəsi" bölməsi |
| Canlı sessiya fərdi tempo (sinxron model ləğvi) | Hər tələbə öz "Növbəti sual" düyməsi ilə öz sürəti ilə irəliləyir, müəllim ÜMUMİ vaxt limiti (1-10 dəqiqə) təyin edir, `.planning/2026-09-08-masterai-live-session-pacing/` | ✅ Tam uc-uca REAL test edilib — bax yuxarı "Canlı Sinif Sessiyası" bölməsi |
| İngestion keyfiyyəti (link JS-render) + sual sayı seçimi | Müəllim hər material yükləməsində ÜMUMİ sual sayını (3-30) təyin edir, JS-render olunan saytlar (SPA) universal gözləmə ilə oxunur, sayt UI naviqasiyası sual generasiyasından xaric edilir, `docs/superpowers/specs/2026-09-08-masterai-ingestion-question-count-design.md`, `.planning/2026-09-08-masterai-ingestion-question-count/` | ✅ Tam uc-uca REAL test edilib (VPS-də) — bax aşağı "İngestion keyfiyyəti" bölməsi |

## Canlı Sinif Sessiyası (Faza 1 — Master NR 1 pilotu)

Mövcud tələbə-yönümlü sistemə TOXUNMADAN əlavə olunmuş paralel alt-sistem:
müəllim sual bankı yaradır → AI sualları çıxarır → canlı sessiya
başladır; tələbələr Kahoot-tərzi cavablayır.

**DİQQƏT — bu bölmənin bir hissəsi TARİXDİR.** Aşağıdakı PIN
istinadları 2026-09-07/09-08 tarixli vəziyyəti təsvir edir. **PIN axını
2026-09-11-də tamamilə silindi** (bax «Qrup çatı = sinif» bölməsi):
sessiya bir qrup çatına bağlıdır, müəllim onu çatdan başladır, tələbə
çatdakı «Qoşul» düyməsindən girir — nə PIN, nə ad yazılır, hesab
məcburidir. `qosul.html` və anonim iştirakçı yolu artıq yoxdur.

**2026-09-07 tarixində TAM UC-UCA REAL TEST edilib** (istifadəçinin real
Windows mühitində, real backend-ə qarşı): sual bankı yaradılması → AI-nın
real 3 sual çıxarması → PIN → tələbənin qoşulması → 3 sualın canlı
göstərilməsi/cavablanması → avtomatik keçid → sessiya bitməsi → host-un
"Sessiya hesabatı" ekranı (yekun sıralama + sual-sual təhlil) — HAMISI
düzgün işlədi. 343 backend test + 32 Flutter test, hamısı keçir.

**Çoxiştirakçılı yoxlama (2026-09-11, əvvəl AÇIQ idi):**
`deploy/diagnostics/live_session_load.mjs` ilə sınanır — N ayrı brauzer
konteksti (ayrı localStorage, ayrı WebSocket) EYNİ ANDA qoşulur və
EYNİ ANDA cavablayır. **PIN axını silindikdən sonra skript çat axınına
keçirildi** (hər tələbə API ilə qeydiyyatdan keçir, kod ilə istək
göndərir, müəllim toplu təsdiqləyir, sonra `sessiya.html?id=N`).

**25 iştirakçı ilə nəticə təmizdir (çat axını ilə təkrarlanıb):**

- hər 4 sualda `total_answers = 25` — heç bir cavab İTMƏYİB
- xal aralığı 0-4, sual sayını aşan yoxdur
- təkrar iştirakçı adı yoxdur, toplu təsdiq 25/25
- qoşulma müddəti ~10.8 saniyə (25 brauzer konteksti)
- server jurnalında **0 xəta** — `server/user_store.py`-dəki sqlite
  kilid narahatlığı bu yükdə ÖZÜNÜ GÖSTƏRMƏDİ

Skript nəticəni MƏTNDƏN yox, `/live/sessions/{id}/report` cavabından
yoxlayır və problem tapsa sıfırdan fərqli kodla çıxır.

**Bağlantı kəsilməsinə davamlılıq (2026-09-11, əvvəl HEÇ sınanmamışdı):**
`deploy/diagnostics/live_session_resilience.mjs` iki ssenarini yoxlayır.
Real sinifdə hər ikisi olur — telefon kilidlənir, müəllimin noutbuku
yuxuya gedir. `ReconnectingSocket` məhz bunun üçün yazılıb, amma heç
vaxt real sınanmamışdı.

- **Tələbənin bağlantısı kəsilib qayıdır:** cavabı və tərəqqisi
  qorunur, «Növbəti sual» işləyir, növbəti sualı cavablaya bilir, host
  gedişatı yenilənir.
  **DÜZƏLİŞ (2026-09-12): burada əvvəl «iştirakçı TƏKRARLANMIR (host-da
  yenə 2 nəfər)» yazılmışdı — bu YANLIŞ idi.** Skript iştirakçıları
  yalnız ÇAP edirdi, yoxlamırdı; nəticə ekrana baxıb qəbul edilmişdi.
  Real produksiyada (sessiya #31) bir tələbə bazada ÜÇ sətirlə göründü.
  Bax aşağı «Dərs: təkrarlanan iştirakçı».
- **MÜƏLLİMİN bağlantısı kəsilir:** tələbələr CAVABLAMAĞA DAVAM EDİR —
  **dərs dayanmır.** Host qayıdanda bağlantı «Bağlıdır» olur və gedişat
  siyahısı özü-özünə yetişir (kəsilmə müddətindəki cavabları göstərir).
  Yəni sessiya host-un soketinə bağlı DEYİL. Bu, pilot üçün vacib
  xəbərdir: müəllimin internetinin anlıq kəsilməsi dərsi öldürmür.

**Uc-uca İNSAN AXINI (2026-09-11):**
`deploy/diagnostics/chat_join_flow.mjs` — tələbə kodu ƏL İLƏ yazır,
müəllim təsdiq düyməsinə BASIR, tələbə çatda sessiyanı görüb qoşulur.
8 addımın hamısı təmiz: kiçik hərflə yazılan kod qəbul olunur, istək
üzvlük yaratmır, üzvə dəvət kodu göstərilmir, tələbə PIN və ad
YAZMADAN sessiyaya girir, lövhədə canlı sessiya xalı görünür, müəllim
lövhədə yoxdur.

**Bu nəyi İSBAT ETMİR:** bir maşındakı brauzer kontekstləridir — real
şəbəkə gecikməsi, mobil rabitə və ayrı-ayrı telefonlar yoxdur. Serverin
eyni anda gələn 25 bağlantını və cavabı düzgün emal etdiyi göstərilib,
şəbəkə davranışı YOX. Master NR 1 kursunda real sınaq dərsi hələ də
planlaşdırılmalıdır — amma artıq "heç sınanmayıb" vəziyyətindən çıxdıq.

Ətraflı tarixçə/qərarlar üçün bax
`.planning/2026-09-07-masterai-live-classroom/progress.md`.

**2026-09-08 tarixində sinxron model tam ləğv edilib (fərdi tempo):**
əvvəlki "hər kəs eyni sualda, 20san sayğac, hamı cavablayanda avtomatik
keçid" modeli əvəzinə indi hər tələbə öz "Növbəti sual" düyməsi ilə öz
sürəti ilə irəliləyir, müəllim sessiya başladanda ÜMUMİ bir vaxt
büdcəsi (defolt/seçim: 1-10 dəqiqə) təyin edir. Real Windows mühitində
(host konsolu vaxt limiti seçici + fərdi tərəqqi siyahısı, tələbə
mənual keçid) TAM TƏSDİQLƏNDİ. Ətraflı bax
`.planning/2026-09-08-masterai-live-session-pacing/progress.md`.

## Ev Təkrarı Rejimi (Faza 2 — asinxron fərdi məşq)

Faza 1-in üzərinə paralel əlavə: müəllim mövcud bir sual bankını
(canlı sessiya üçün yaradılmış) bir qrup çata "ev tapşırığı" kimi son
tarixlə təyin edir (veb host konsolu VƏ mobil çat ekranı — hər ikisi
`is_teacher` bayrağı ilə açılır), tələbə "Tapşırıqlarım" ekranında görüb
öz sürəti ilə həll edir (WebSocket yoxdur, vaxt sayğacı yoxdur, hər
cavabdan sonra dərhal geri bildirim, fasilə/davam mümkün, tək cəhd),
müəllim "Tapşırıq hesabatları" ekranında hər tələbənin statusunu
(gözləyir/davam edir/tamamlanıb+xal) görür.

**2026-09-07 tarixində TAM UC-UCA REAL TEST edilib**: müəllim (veb)
"alma" sual bankından bir çata tapşırıq təyin etdi → tələbə (Android
emulyator, ayrı hesab) "Tapşırıqlarım"da gördü, açıb HƏLL ETDİ →
müəllim hesabatda REAL statusları gördü (özü "gözləyir", tələbə
"tamamlanıb" ✓). 381 backend test + 39 Flutter test, hamısı keçir.
Bu prosesdə real özü-özünə tapılan bir funksional boşluq (hesabata
baxmaq üçün UI unudulmuşdu) aşkarlanıb dərhal düzəldildi.

**Çata qoşulma UI-ı** (real testdə tapılan boşluq, dərhal düzəldildi):
çat siyahısı ekranına "Çata qoşul" ikonu əlavə olundu — çat ID-sini
(mövcud çat sətirlərinin subtitle-ında görünür) əl ilə yazıb özü-özünə
qoşulmaq mümkündür (`POST /chats/{id}/join`, mövcud backend
endpoint-i, dəyişiklik yoxdur).

Növbəti planlaşdırılan fazalar (istifadəçi ilə razılaşdırılıb): Fərdi
tələbə tarixçəsi, Çox-müəllimli idarəetmə, Sual redaktə/təsdiq ekranı.
Ətraflı tarixçə/qərarlar üçün bax
`.planning/2026-09-07-masterai-homework-mode/progress.md`.

## Fərdi tələbə tarixçəsi (Faza 3)

Faza 1+2-nin üzərinə: tələbənin canlı sessiya VƏ ev tapşırığı
nəticələri eyni xronoloji siyahıda birləşdirilir. Tələbə "Mənim
tarixçəm" ekranında öz nəticələrinə baxır, müəllim "Fərdi tələbə
tarixçəsi" ekranından (çat seç → üzv seç) istənilən tələbənin
tarixçəsinə baxır (yalnız ortaq çatı olan tələbələr üçün icazə verilir).

**Real arxitektura boşluğu tapılıb düzəldilib:** `live_participants`
əvvəllər `users`-a bağlı deyildi (PIN qoşulması qəsdən hesabsız idi).
Aralıq həll kimi join mesajına KÖNÜLLÜ `token` sahəsi əlavə olunmuşdu.

**2026-09-11-də bu tam bağlandı:** anonim yol silindi, token
MƏCBURİDİR, `add_participant` `user_id`-siz çağırıla bilmir. Yəni
`user_id IS NULL` olan sətir artıq YARANA BİLMƏZ; canlı bazadakı
köhnə anonim sətirlər qalır və `list_participations_for_user` onları
onsuz da qaytarmır.

**Vəziyyət (2026-09-07):** Tam uc-uca REAL test edilib (canlı sessiya +
ev tapşırığı + hər iki tərəfin — tələbə "Mənim tarixçəm", müəllim "Fərdi
tələbə tarixçəsi" — ekranları). Ətraflı bax
`.planning/2026-09-07-masterai-student-history/progress.md`.

**Veb versiyasında təsdiq (2026-09-11):** "join-after-login" zənciri
Flutter-dən veb-ə keçiddən sonra ilk dəfə uc-uca yoxlandı — daxil olmuş
tələbə PIN ilə qoşuldu, 4 sualı cavabladı, nəticə `tarixce.html`-də
göründü ("1 nəticə · 3/4 düzgün (75%)", növü "Canlı sessiya").

Həmin gün PIN axını silindi və zəncir daha da sadələşdi: tələbə onsuz
da daxil olmuş vəziyyətdə çatdan qoşulur, yəni «könüllü token»
anlayışı qalmadı — hər nəticə bir hesaba bağlıdır.

## Çox-müəllimli idarəetmə (Faza 4)

Ayrıca `is_admin` bayrağı (`is_teacher`-in eyni `ALTER TABLE` naxışı) —
`is_admin` istifadəçilər tətbiq daxilindən (`POST /admin/teachers`,
e-poçtla) başqa bir istifadəçini müəllim edir/çıxarır. **Diqqət:** bu,
mövcud `require_admin` (API-açarlı, `ADMIN_API_KEY`, n8n
avtomatlaşdırması üçün, `/admin/stats`) İLƏ QARIŞDIRILMAMALIDIR — tamam
ayrı iki icazə mexanizmidir.

**Bootstrap problemi:** `is_admin` hamıda `false` başlayır — İLK admin
mütləq VPS-də əl ilə (`UserStore.set_admin`, `set_teacher`-in eyni
naxışı) təyin edilməlidir, tətbiq daxilindən heç vaxt ilk admin yaradıla
bilməz.

**Vəziyyət (2026-09-07):** Tam uc-uca REAL test edilib (bootstrap admin
təyinatı VPS-də, e-poçtla müəllim təyini, müəllim siyahısının
göstərilməsi). Ətraflı bax
`.planning/2026-09-07-masterai-multi-teacher-management/progress.md`.

## Sual redaktə/təsdiq ekranı (Faza 5)

Müəllim veb host konsolunda "Hazırdır" statuslu hər sual bankının
sualları siyahısına baxıb hər hansı birinin mətnini, 5 variantını,
düzgün cavabını və izahını redaktə edir və ya silir. Məcburi təsdiq
addımı YOXDUR — sual bankı indiki kimi "ready" olan kimi dərhal
sessiya/tapşırıq üçün istifadə oluna bilər, redaktə isteğe bağlıdır.

**Vəziyyət (2026-09-07):** Tam uc-uca REAL test edilib (sual mətni/
variant/düzgün cavab dəyişdirilib saxlanılıb). Bununla istifadəçinin
orijinal 4-fazalı roadmap-ı (Ev Təkrarı Rejimi → Fərdi tələbə
tarixçəsi → Çox-müəllimli idarəetmə → Sual redaktə/təsdiq) TAM başa
çatdı. Ətraflı bax
`.planning/2026-09-07-masterai-question-edit/progress.md`.

## Nailiyyət nişanları + Liderlik lövhəsi (Faza 6)

Vizual dizayn yenilənməsindən (aşağı bax) sonra brainstorming skill-i ilə
razılaşdırılan ikinci layihə: 5 sabit nişan (`ilk_addim`, `yuz_faiz`,
`fenn_ustasi`, `suretli_eqli`, `silsile_5`) mövcud tarixçə datasından
TƏNBƏL (hər `GET /badges/me` çağırışında yenidən) hesablanır, tələbə
"Mənim tarixçəm" ekranındakı 🏆 ikonundan "Nailiyyətlərim" ekranına
baxır. Hər qrup çatının içindəki 🏆 ikonu isə o çatın liderlik lövhəsini
açır. **2026-09-11-ə qədər yalnız ev tapşırığı xalları sayılırdı**
(canlı sessiyalar heç bir çata bağlı deyildi). Sessiya çata bağlandıqdan
sonra lövhə hər iki mənbəni toplayır və müəllim siyahıdan çıxarılır —
bax «Qrup çatı = sinif» alt-layihəsi.

**Vəziyyət (2026-09-08):** Backend 461/461 pytest (bu sandbox-da real
icra) + Flutter tərəfi istifadəçinin real Windows mühitində tam
uc-uca TƏSDİQLƏNDİ (Nailiyyətlərim + Liderlik lövhəsi ekranları hər
ikisi işlək). Ətraflı bax
`.planning/2026-09-08-masterai-badges-leaderboard/progress.md`.

## Vizual dizayn yenilənməsi

4-fazalı funksional roadmap tam bitdikdən sonra brainstorming skill-i ilə
hazırlanan dizayn yeniləməsi: `google_fonts` (başlıqlar üçün Nunito,
mətn üçün Inter), `ThemeExtension<AppSubjectColors>` ilə 6 fənn üçün
aksent rəng (mövcud `ColorScheme.fromSeed` struktur rənglərinə
TOXUNULMADAN), `ThemeMode.system` (işıq/tünd rejim), canlı sessiya/ev
tapşırığı həll ekranlarının "sakit əsas + enerjili" gücləndirilməsi
(böyük/qalın düymələr, elastik pop animasiyaları).

**Real bug tapılıb düzəldilib:** tək-iştirakçılı canlı sessiyada
`live_session_runner.py`-nin mövcud davranışı (bütün iştirakçılar cavab
verən kimi DƏRHAL növbəti suala keçid) nəticə ekranının gözlə görünməyəcək
qədər qısa çıxmasına səbəb olurdu (bu, bu sessiyada YARADILAN reqressiya
DEYİL — server məntiqi dəyişdirilmədi). Client-tərəfli minimum-göstərmə
taymeri (2 saniyə) ilə düzəldildi.

**Vəziyyət (2026-09-08):** Phase 1-5 (font, `AppSubjectColors`, tünd
rejim, mövcud ekranlara fənn rəngi tətbiqi, canlı sessiya/həll
ekranlarının enerjili animasiyası + yuxarıdakı bug düzəlişi) real
mühitdə TAM TƏSDİQLƏNDİ. Ətraflı bax
`.planning/2026-09-08-masterai-visual-design/progress.md`.

## İngestion keyfiyyəti (link JS-render) + sual sayı seçimi

Müəllim hər material (PDF/link/şəkil) yükləməsində ÜMUMİ sual sayını
(3-30, defolt 10) təyin edir — `pipeline.generate_quiz` bunu
`target_question_count` kimi qəbul edib chunk-lara görə lazımi
`questions_per_chunk`-ı özü hesablayır, dedup-dan sonra tələb olunan
sayda kəsir (material qısadırsa xəbərdarlıqla az sayla qəbul edir).

Sayt (link) materialının JS-render olunan (SPA) saytlarda oxunması
universal `readyState`+mətn-sabitləşmə gözləməsi ilə yaxşılaşdırıldı,
`--disable-dev-shm-usage` bayrağı əlavə olundu. Sual generasiyasının
sayt UI naviqasiyasından (tab adları, status nişanları, düymələr) sual
düzəltməməsi üçün `_extract_text` `<main>`/`<article>` varsa YALNIZ
ondan mətn çıxarır, sistem prompt-una da açıq təlimat əlavə olundu.

**Vəziyyət (2026-09-08):** Tam uc-uca REAL VPS-də test edilib
(`e-qanun.az` linki) — sual sayı seçimi, link yükləməsi, sual
generasiyası, canlı sessiya, hesabat HAMISI işlədi. Yol boyu VPS-in
Chrome/disk/swap infrastrukturu da düzəldildi (bax aşağı "Dərs: VPS-də
Chrome/Selenium quraşdırma"). Ətraflı bax
`.planning/2026-09-08-masterai-ingestion-question-count/progress.md`.


## Quiz UX yenilənməsi (2026-09-12) — «əsl tədris tətbiqi» hissi

İstifadəçi şikayəti: «sayt əsl education app havası vermir», quizlər
rəngarəng olsun, sayt «AI ilə hazırlanmış kimi görünməsin». Üç səbəb
tapıldı, ikisi ölçüləbilən:

1. **Quiz ekranı dizayn olunmuş komponenti İŞLƏTMİRDİ.** Hər iki ekran
   (canlı sessiya + ev tapşırığı) variantları `btn btn--secondary` ilə
   çəkirdi — ekranda beş bərabər boz düymə. `.option` anatomiyası
   `components.css`-də var idi və YALNIZ açılış səhifəsində işlədilirdi.
2. **Palitra AI-nın standart görünüşü idi:** isti krem fon (`#FAFAF8`) +
   Source Serif başlıq. İndi sərin qrafit + **Archivo**.
3. **Fənn rəngləri istifadəsiz qalırdı** — yalnız kartın 3px kənarında.

Yeniliklər: `quiz-options.js` (hər iki ekran üçün PAYLAŞILAN variant
çəkilişi), A-E üçün beş rəngli hərf nişanı, sual-sual seqment tərəqqisi,
`.verdict` bloku, `.streak` (2+ ardıcıl), `.score-ring`
(`conic-gradient`, kitabxanasız), `.rank` sıralama sətirləri.

**Rəng intizamı qalır:** fənn/variant rəngi YALNIZ məzmunu işarələyir,
düymə rəngi kimi işlədilmir. Qırmızı və yaşıl variant rəngi kimi
İŞLƏDİLMİR — onlar səhv/düzgün siqnallarıdır.

**Şrift mənbədən yoxlandı:** üç namizədin `cmap` cədvəli oxundu —
Figtree-də `Ə` və `ə` YOXDUR (Manrope ilə eyni tələ), Archivo 14/14.

**Brauzer render-i üç qüsur tapdı** (kod testləri tuta bilməzdi): xal
dairəsində faiz mətni halqanın üstünə düşürdü, D variantının qırmızı
rəngi «səhv» siqnalı ilə toqquşurdu, açılış səhifəsində hərf nişanı boz
fonda ağ hərflə görünməz olardı.

**Mövcud testlər üç səhvimi tutdu:** emoji ikon kimi (`✓`/`✗` → sprite
`i-x` əlavə edildi), uzun tire, təyin olunmamış token.

**İkinci iterasiya (eyni gün): yaşıl + sarı + qara.** Mavi tamamilə
getdi (favicon və 17 `theme-color` metası daxil). Üst zolaq QARADIR,
cari səhifə sarı ilə işarələnir. İki semantik toqquşma həll edildi:
«düzgün» brend yaşılının doymuş variantıdır (ayrı yaşıl deyil),
xəbərdarlıq sarıdan NARINCIYA keçdi (sarı indi brend aksentidir), və
«seçildi, gözlənilir» vəziyyəti RƏNGSİZ edildi - yoxsa «seçilmiş» ilə
«düzgün» iki solğun yaşıl olardı. 22 rəng cütünün WCAG kontrastı
hesablanıb, hamısı AA keçir.

Ətraflı: `docs/superpowers/specs/2026-09-12-masterai-quiz-ux-redesign.md`.
**Deploy EDİLMƏYİB** — istifadəçinin təqdimatı səbəbindən sistem
donduruldu.

## Veb-first keçidi (2026-09-09) — ƏSAS ARXİTEKTURA DƏYİŞİKLİYİ

Flutter tətbiqi arxivləşdirildi, yerini statik veb sayt tutdu.

**Həlledici səbəb:** Flutter app-ın release imzalama açarı yox idi və
Play Store-a heç vaxt dərc olunmamışdı — yəni **real tələbəyə çatmaq
yolu YOX idi**, bütün testlər tərtibatçının öz emulyatorunda olmuşdu.
Sayt isə link paylaşılan an işləyir. İkinci arqument: plan onsuz da 21
ekranın hamısını yenidən yazmağı nəzərdə tuturdu, ona görə keçidin
əlavə xərci azdır.

**Backend TOXUNULMADI** — `server/` və `pipeline/` dəyişmədi.

### Texniki qaydalar

- **Build addımı yoxdur.** npm, bundler, Flutter SDK — heç biri.
  Fayllar olduğu kimi nginx tərəfindən verilir (`saas_core` naxışı).
- **`tokens.css` yeganə rəng/ölçü mənbəyidir.** Digər CSS fayllarında
  birbaşa hex rəng və ya ölçü yazılmır. `tests/test_web_design_system.py`
  bunu avtomatik yoxlayır.
- **İstifadəçi mətni HEÇ VAXT `innerHTML`-ə verilmir**, yalnız
  `textContent` — çat məzmununu başqa istifadəçilər yazır.
- **Lokal yoxlama üçün server MƏCBURİDİR:** `file://` ilə ES modulları
  brauzer tərəfindən CORS səbəbi ilə bloklanır (real Chromium testi ilə
  təsdiqləndi). `py -m http.server 8123`.

### Bu keçidin gətirdiyi qazanc: frontend indi bu mühitdə icra olunur

Flutter kodunu bu sandbox-da işə salmaq MÜMKÜN DEYİLDİ (SDK yoxdur) —
hər şey istifadəçinin kompüterində yoxlanılırdı. İndi Node 22 ilə JS
testləri, Chromium ilə real render yoxlaması burada aparılır. Bu, dərhal
bir neçə bug tapdı, o cümlədən:

- **`hidden` atributu işləmirdi:** `.notice { display: flex }` brauzerin
  `[hidden] { display: none }` qaydası ilə eyni spesifiklikdədir və
  sonra gəldiyi üçün qalib gəlirdi. Nəticədə boş qırmızı xəta zolaqları
  HƏR səhifədə görünürdü. Nə HTML, nə CSS testi bunu tuta bilməzdi.

### nginx-də iki gizli tələ (testlə bağlanıb)

1. **Yol kökü siyahısı:** statik sayt və API eyni domeni paylaşır.
   Backend-ə yeni ÜST SƏVİYYƏLİ endpoint əlavə edilib
   `deploy/nginx-masterai.conf`-dakı siyahıya yazılmasa, nginx onu
   statik fayl kimi axtarar → 404. `tests/test_nginx_routes.py`.
2. **Regex location prefiksdən üstündür:** `ws` API regex siyahısına
   salınsa `/ws/` bloku heç vaxt işə düşməz, `Upgrade` başlıqları
   ötürülməz və WebSocket handshake-i SÜKUTLA sınar (adi 200 kimi
   görünər).

### Diaqnostika alətləri

```bash
.venv/bin/python -m http.server 8123 --bind 127.0.0.1 --directory web &
.venv/bin/python deploy/diagnostics/check_pages_in_browser.py   # JS xətaları
.venv/bin/python deploy/diagnostics/screenshot_pages.py          # görünüş

# Uc-uca (real backend 8125 + npm i playwright-core lazımdır):
node deploy/diagnostics/chat_join_flow.mjs <müəllim tokeni>        # insan axını
node deploy/diagnostics/live_session_load.mjs <token> 25 <bankId>  # 25 tələbə
node deploy/diagnostics/live_session_resilience.mjs <token> student # bağlantı
node deploy/diagnostics/live_session_resilience.mjs <token> host
```

**`npm i playwright-core` repoya girmir** — `.gitignore`-dadır.
Skriptlər `createRequire(cwd)` ilə paketi istənilən qovluqdan tapır,
yəni «build addımı yoxdur» qaydası pozulmur.

## Giriş formatları (pipeline)

Sistemimiz üç növ materialı dəstəkləyir:
- **Sayt linki** — BeautifulSoup/Selenium scraping
- **PDF** — pypdf ilə mətn çıxarılması
- **Şəkil** — pytesseract OCR

## Bilinən risklər (production-dan əvvəl həll edilməli)

- **WebSocket JWT query param-da (`?token=...`)** — brauzer WebSocket
  API-si custom header dəstəkləmədiyi üçün belə edilib.
  **YARIMÇIQ HƏLL EDİLİB (2026-09-10):** jurnal sızması bağlandı
  (`server/log_redaction.py` — `token`/`ticket`/`api_key`/`Bearer`/
  `X-Admin-Key` dəyərləri `***` ilə əvəzlənir). Real yoxlama HƏR İKİ
  icra yolunda aparıldı: plain uvicorn VƏ production-la eyni
  `gunicorn -k uvicorn.workers.UvicornWorker` — hər ikisində jurnalda
  `token=***`, tam token 0 dəfə.
  **AÇIQ QALIR:** token hələ URL-dədir. Tam həll qısaömürlü WS "ticket"
  tokenidir (bax `docs/superpowers/specs/2026-09-02-chat-messaging-design.md`,
  bölmə 4) — `ReconnectingSocket` hər yenidən qoşulmada yeni ticket
  istəyəcəyi üçün bu, canlı sessiya və çat bağlantısına toxunan ayrıca
  işdir.
  **Dərs (filtri yazarkən çıxdı):** filtri root HANDLER-inə qoşmaq
  İŞLƏMİR — `uvicorn.access` üçün `propagate=False`-dur və
  `UvicornWorker` onun `handlers`-ini əvəz edir. Filtr LOGGER-ə
  qoşulmalıdır; 12 vahid test keçsə də real icra bunu açdı.
- ~~`_notify_admin_webhook()` real production-da hələ sınanmayıb~~ —
  **✅ TƏSDİQLƏNDİ (2026-09-03):** Flutter app-ın real mühit testində
  (qrup çatına sayt linki yükləndi, emal uğursuz oldu — bax aşağıdakı
  "Dərs: real material uğursuzluğu" bölməsi) backend real şəkildə
  `_notify_admin_webhook()`-u çağırdı və Telegram-a bildiriş REAL
  gəldi (istifadəçi təsdiqlədi). Uc-uca zəncir (backend material
  emalı → n8n webhook → Telegram) indi tam real şəraitdə yoxlanılıb.

## Dərs: təkrarlanan iştirakçı — hər WS bağlantısı yeni sətir yazırdı (2026-09-12)

Real dərsdə tapıldı. Tələbə (Amil) sessiyaya qoşuldu, səhifəni bir neçə
dəfə yenilədi. Bazada:

```
sessiya #31: chat=5 yaradan=2 status=active
  iştirakçı: Tələbə A | user_id: 5 | 07:02:48
  iştirakçı: Tələbə A | user_id: 5 | 07:03:02
  iştirakçı: Tələbə A | user_id: 5 | 07:04:15
```

Üç sətir — jurnaldakı üç `[accepted]` `/play` bağlantısı ilə dəqiq
üst-üstə düşür. `add_participant` sadə `INSERT` idi və `/play`
soketinin HƏR açılışında çağırılırdı.

**Zərər üç yerdədir:**
1. Sessiya hesabatındakı sıralama (`rankings`) `participant_id` ilə
   qurulur — bir adam üç sətirlə, balı üç yerə bölünmüş görünür.
2. Tələbə qayıdanda cavab sayı YENİ sətirdə sıfır olduğu üçün yenidən
   0-cı sualdan başlayır.
3. Host siyahısı `participant_joined` hadisələrini `concat` edir —
   ekranda eyni ad təkrarlanır.

Liderlik lövhəsi **təsirlənmir**: `chat_scores_by_user` `user_id` üzrə
qruplaşdırır, yəni təkrarlar onsuz da birləşir.

**Düzəliş:** `add_participant` artıq TAP-VƏ-YA-YARATdır — (sessiya,
istifadəçi) cütü üçün bir sətir; `joined_at` ilk qoşulmanı saxlayır,
`display_name` cari ada yenilənir. `join_session` təkrar qoşulmada
host-a hadisə GÖNDƏRMİR. Mövcud korlanmış sətirlər üçün ayrıca təmir
skripti var (aşağı).

**Niyə əvvəl tutulmadı — iki ayrı səbəb:**

- **Diaqnostika ekrandan oxuyurdu.** `live_session_resilience.mjs`
  iştirakçı adlarını `console.log` edirdi, heç nə yoxlamırdı; insan
  siyahıya baxıb «iki nəfər, təmiz» demişdi. İndi skript təkrarı özü
  tutur və tapsa sıfırdan fərqli kodla çıxır.
- **Testlərdə `user_id` əhəmiyyətsiz sabit idi.** Fixture-lar Əli,
  Vəli və Səbinəyə EYNİ `user_id=1` verirdi — üç ayrı adam bir hesabla.
  Belə fixture ilə «eyni istifadəçi iki dəfə qoşulur» ssenarisi heç
  vaxt yaranmırdı. Düzəlişdən sonra 8 test dərhal sındı; hamısı
  fixture səhvi idi, davranış yox.

**Təmir skripti (canlı dataya toxunur, ƏL İLƏ işlədilir):**

```bash
python3 deploy/repair_duplicate_participants.py live_sessions.db          # göstər
python3 deploy/repair_duplicate_participants.py live_sessions.db --apply  # yaz
```

Ən erkən sətir qalır, qalanların cavabları ona köçür, eyni sual iki
sətirdə cavablanıbsa İLK cavab saxlanılır, `user_id IS NULL` (köhnə
anonim PIN) sətirlərə TOXUNULMUR. Bitmiş sessiyanın SAXLANMIŞ hesabatı
birləşmədən sonra köhnəlir (sıralama silinmiş `participant_id`-lərə
istinad edir) — `--recompute-reports question_sets.db` onu yenidən
hesablayır; bu addım venv tələb edir, çünki `question_set_store`
`pipeline.models`-u idxal edir. **Avtomatik miqrasiya QƏSDƏN edilmədi:** birləşdirməni geri
qaytarmaq yalnız backup-dan mümkündür, servis start-ında sükutla
işləməməlidir. 15 test (`tests/test_repair_duplicate_participants.py`), CLI-nin özü
subprocess kimi də sınanır.

**Skriptin özü real istifadədə İKİ dəfə sındı** — hər ikisi eyni kök
səbəbdən: skript yalnız import edilərək sınanmışdı.
1. Birbaşa icrada `sys.path[0]` `deploy/` olur → `No module named
   'server'`. pytest `pythonpath = ["."]` ilə işlədiyi üçün görmürdü.
2. Birləşmə yazıldıqdan sonra ikinci icrada baza artıq TƏMİZ olur,
   skript «təkrar yoxdur» deyib erkən çıxır və köhnəlmiş hesabata
   ÇATMIR. `--sessions 31` bunun üçün əlavə edildi.

**PRODUKSİYADA TƏTBİQ EDİLDİ (2026-09-12), nəticə BAZADAN yoxlanıldı:**

| Yoxlama | Əvvəl | Sonra |
|---|---|---|
| Sessiya #31 iştirakçı sətri | 3 (id 20, 21, 22) | 1 (id 20) |
| Cavab | 10 (5 real + 5 təkrar) | 5 |
| Hesabat sıralaması | üç «Amil», bölünmüş bal | bir Amil, 1/5 |

Saxlanılan sətrin `joined_at`-i ilk qoşulmadır (07:02:48). Backup:
`/root/backup-live-2026-09-12-0827.db`. Servis restart edilib, yəni
tap-və-ya-yarat davranışı canlıdır.

**HƏLƏ TƏSDİQLƏNMƏYƏN:** real telefonda «bir sual cavabla → səhifəni
yenilə → müəllim ekranında bax» addımı. Baza və jurnal düzəlişi
sübut edir, EKRANDA nə göründüyünü isə yalnız insan təsdiq edə bilər
(bu dərsin əsas dərsi məhz budur — ekran və baza ayrı şeylərdir).

## Dərs: bütün Store sinifləri `threading.Lock`/`RLock` işlədir

`sqlite3.connect(path, check_same_thread=False)` YALNIZ Python-un thread-
yoxlamasını söndürür, bağlantını thread-safe ETMİR (bax
`server/user_store.py` və digər Store-ların modul qeydi). Bu, real
WebSocket inteqrasiya testində (2 istifadəçi eyni anda cavablayır) sqlite
korlanmasına (`OperationalError: cannot commit`) səbəb oldu — real
tək-prosesli `uvicorn` deploy-unda bu problem YOXDUR (təsdiqlənib, bax
`.planning/2026-09-02-masterai-quiz-orchestration/`), amma çoxlu-thread
test mühitlərində (Starlette `TestClient`-in hər WebSocket bağlantısını
ayrı OS thread-ində işlətməsi) və gələcək `--workers`/çoxlu-thread
ssenarilərində qorunmaq üçün **hər yeni Store sinfi də daxili kilid
işlətməlidir** (nested public-metod çağırışı varsa `RLock`, yoxdursa
sadə `Lock`).

## Dərs: real deploy zamanı rast gəlinən tələlər (VPS-ə aid, kod problemi deyil)

1. **VPS-dəki `/opt/pr-agent/repo` checkout-u `main` branch-indədir** —
   bizim işimiz `claude/ai-engineering-monthly-project-g5cg2y`-dadır.
   `git pull` sükutla `main`-i yeniləyir, `masterai/` görünmür. Deploy-dan
   əvvəl HƏMİŞƏ `git checkout claude/ai-engineering-monthly-project-g5cg2y`
   (və ya işlənən branch) yoxla.
2. **`ufw` yalnız `22`+`443` icazə verirdi, `80` YOX idi** — certbot-un
   HTTP-01 doğrulaması (`/.well-known/acme-challenge/...`) port 80
   tələb edir, "Timeout during connect (likely firewall problem)" xətası
   verdi. Həlli: `ufw allow 80/tcp`. Digər `prdostu.com` alt-domenləri
   üçün də bu VPS-də eyni yoxlama edilməlidir.
3. **n8n MCP-nin credential yaratma aləti YOXDUR** (təhlükəsizlik
   səbəbindən) — `httpHeaderAuth` kimi kredensiallar yalnız n8n UI-dan
   əl ilə yaradıla bilər, sonra `update_workflow`-un `setNodeCredential`
   əməliyyatı ilə node-a bağlanır. UI-da "Name" sahəsi HEADER ADI-dır
   (məs. `X-Admin-Key`), kredensialın öz adı ayrı sahədir (başlıq) —
   qarışdırılması asandır.
4. **Bu VPS-in DigitalOcean abunəliyi bitib deaktiv olsa, BEŞ şey eyni
   anda düşür** — masterai, dildostu-live, masternr1 (aktiv pilot!),
   n8n VƏ **mediapulse.az** (`saas_core/`, `gunicorn`+`pr-agent`,
   `/opt/saas_core/`), hamısı `<SERVER_IP>`-u paylaşır.
   **2026-09-10 düzəlişi:** bu bənd əvvəl "DÖRD" yazırdı və mediapulse-u
   sadalamırdı — halbuki `saas_core/CLAUDE.md` onun da eyni serverdə
   olduğunu göstərir. Bu, risk qiymətləndirməsini dəyişir: mediapulse-un
   aktiv müştərisi dövlət qurumudur, yəni bu maşında disk dolması
   və ya abunəlik kəsilməsi nazirlik müştərisi olan sistemi də çökdürür. Real hadisə: abunəlik bitdi,
   VPS tam əlçatmaz oldu (SSH/HTTPS/ping — HAMISI timeout), Flutter
   app-da real telefonda "Bağlantı xətası" bununla izah olundu (kod
   bug-ı DEYİL). Bu VPS-in abunəlik/ödəniş statusu digər layihələrdən
   asılı olmayaraq mütəmadi yoxlanılmalıdır — bir hesabın bitməsi üç
   layihəni birdən öldürür.
5. **`tesseract-ocr` VPS-də quraşdırılmayıb** — real telefonda şəkil
   materialı yükləndikdə "Material emalı uğursuz oldu: tesseract is
   not installed or it's not in your PATH" xətası verdi (`pytesseract`
   sistemdə `tesseract` binarını axtarır, Python paketi kifayət etmir).
   Həlli: `apt install -y tesseract-ocr` (servisi restart etmək lazım
   deyil, hər çağırışda binar yenidən axtarılır). `requirements.txt`-də
   bu sistem asılılığı qeyd olunmayıb — gələcək VPS-lərdə deploy
   skriptinə (`deploy_on_droplet.sh`) əlavə edilməlidir.
6. **VPS-in diski (10GB) çox kiçikdir, `tesseract-ocr`-un eyni növ
   boşluğu Chrome/Selenium üçün də təkrarlandı, amma qat-qat ağır
   nəticələrlə (2026-09-08):** JS-render (link ingestion) düzəlişini
   real sınayanda VPS-də Chrome/chromedriver ÜMUMİYYƏTLƏ yox olduğu
   üzə çıxdı. Quraşdırma cəhdi zamanı VPS-in diski onsuz da demək olar
   TAM dolu idi (8.7G/8.7G) — `journalctl` tək başına 876M tuturdu.
   Bu zaman əlavə edilən 2GB-lıq ehtiyat swap fayl diski TAM doldurub
   `masterai` servisini ÇÖKDÜRDÜ (crash-loop, "No usable temporary
   directory found"). Sonra snap-paketli `chromium-browser` "session
   not created: DevToolsActivePort file doesn't exist" verdi (snap-ın
   sərt AppArmor confinement-i /tmp-ə tam çıxışı bloklayır,
   `--disable-dev-shm-usage` bunu HƏLL ETMİR) — snap chromium silinib
   Google Chrome-un rəsmi `.deb` paketi qoyuldu (bu da X11/GL asılılıq
   zənciri ilə diski yenidən doldurub `dpkg` xətası verdi, `apt clean`
   + `apt --fix-broken install` ilə tamamlandı). **Hazırkı sabit
   vəziyyət:** `/usr/bin/google-chrome` quraşdırılıb, jurnal ölçüsü
   `SystemMaxUse=150M` ilə məhdudlaşdırılıb, VPS-in ehtiyat swap-ı
   YOXDUR (yalnız əvvəlcədən mövcud `/swapfile`, 1.1G). Disk daim
   ~90%+ dolu qalır — **gələcəkdə bu VPS-də hər hansı `apt install`
   əməliyyatından ƏVVƏL mütləq `df -h /` yoxlanmalıdır**, əks halda
   eyni səbəbdən masternr1 (aktiv pilot!) daxil bütün servislər risk
   altına düşür.
   **Runbook: `deploy/VPS_MAINTENANCE.md`** — ölçmə skripti
   (`deploy/vps_disk_report.sh`, heç nə silmir), üç təbəqəli təmizlik
   (təhlükəsiz keş → qərar tələb edən backup → YALNIZ restartdan sonra
   `apt autoremove`), restart pəncərəsi və pre-flight. Restartın ən
   böyük riski `systemctl is-enabled`-dir: `disabled` servis qalxmır və
   HEÇ BİR xəta vermir.

## Təsdiq: Claude fallback-ı real emalda işləyir (2026-09-10)

Günlərdir açıq qalan sual bağlandı. Canlı saytdan yaradılmış sual
bankının emalında jurnal göstərdi:

```
3 llm_failed provider=groq
3 llm_ok     provider=claude
7 llm_ok     provider=groq
```

Groq 10 chunk-dan 3-ündə sındı və hər üçünü Claude götürdü.
`llm_all_failed` YOXDUR — heç bir chunk itmədi. Yəni
`complete_with_fallback` zənciri production-da real yüklə işləyir.

**Bunu görmək üçün əvvəlcə jurnal konfiqurasiyası düzəldilməli idi**
(bax aşağı): `llm_ok` INFO səviyyəsindədir və layihədə heç bir
`logging.basicConfig` olmadığı üçün root logger WARNING-də qalırdı —
uğursuzluqlar görünürdü, uğurlar YOX. Aylarla "Claude işləyirmi?"
sualının cavabsız qalmasının səbəbi bu idi.

Eyni emal veb tərəfin də uc-uca sübutu oldu: giriş → forma → multipart
yükləmə → fon emalı → 10 saniyəlik avtomatik yenilənmə → "Hazırdır".

## Dərs: Selenium keşi diski yeyir (2026-09-10)

Link ingestion (JS-render) işə düşəndən sonra `/root/.cache/selenium`
**845 MB**-a çatmışdı — Selenium Manager hər işə düşəndə brauzer/driver
versiyalarını yükləyib keşləyir və köhnələri özü təmizləmir.

Bu, 8.65 GB-lıq, beş servis daşıyan maşında ciddi problemdir: disk 98%-ə
çatmışdı və deploy bloklanmışdı. Silmək təhlükəsizdir (keşdir, özü
yenidən yaranır), amma **yenidən böyüyəcək**.

```bash
du -sh /root/.cache/*        # ölç
rm -rf /root/.cache/selenium # təmizlə (növbəti emal driver-i yenidən yükləyər)
```

Mütəmadi yoxlanmalıdır. Kök həll diskin böyüdülməsidir.

## İcazə xəritəsi (2026-09-10-da tam yoxlanılıb)

`/live/*`-da beş endpoint qapısız tapıldıqdan sonra BÜTÜN marşrutlar
bir-bir yoxlandı. Hazırkı vəziyyət:

| Qapı | Say | Nümunə |
|---|---|---|
| Qəsdən açıq | 2 | `POST /auth/register`, `POST /auth/login` |
| Yalnız giriş + gövdədə üzvlük/sahiblik | 22 | `/chats/*`, `/homework/*`, `/history/me` |
| Müəllim (asılılıq) | 10 | bütün `/live/*` |
| Müəllim (sətiriçi) | 2 | `POST /homework/assignments`, `GET /history/student/{id}` |
| Admin | 4 | `/admin/*` (ikisi API açarı, biri `is_admin`) |
| WebSocket (öz məntiqi) | 3 | `/ws/chat/*`, `/ws/live/*` |

**Ayrıca yoxlanılıb (ən riskli olanlar):**
`POST /homework/attempts/{id}/answer` → `attempt["student_id"] != user["id"]`
ilə 403 verir (başqasının cəhdini cavablamaq mümkün deyil);
`POST /chats/{id}/quiz/start` → yalnız materialı yükləyən başlada bilir;
çat endpointləri `member_ids` ilə üzvlüyü yoxlayır.

**`tests/server/test_endpoint_guards.py`** bu xəritəni qoruyur: hər yeni
marşrut ya qapıdan keçməli, ya da SƏBƏBİ ilə `PUBLIC_ROUTES`-a
yazılmalıdır. Test qapını müvəqqəti çıxarmaqla real olaraq sınanıb —
`GET /badges/me` dərhal tutuldu.

## Dərs: üç bug yalnız BRAUZER RENDER-i ilə tapıldı (2026-09-10)

Veb səhifələrin nə pytest, nə pyflakes tuta bilmədiyi üç real səhvi
Chromium-da render etməklə tapıldı. Naxış eynidir: **kod işləyir, amma
ekranda səhv şey görünür.**

1. **Nişan ikonu adı mətn kimi çap olunurdu.** `nailiyyetler.html`
   `state__icon` div-inə `badge.icon`-u `textContent` kimi yazırdı,
   yəni ekranda `seedling`, `school`, `bolt` sözləri nəhəng hərflərlə
   görünürdü. Sprite (`assets/icons.svg`) bu ikonları onsuz da
   saxlayırdı — sadəcə JS ona bağlanmamışdı.
   → İndi `TestBadgeCatalogContract` hər nişan ikonunun sprite-da
   mövcud olduğunu VƏ ekranın ikonu çəkdiyini yoxlayır.

2. **Sabit `width` telefonda üfüqi sürüşmə yaradırdı.** `giris`,
   `qeydiyyat` və `qosul` səhifələri `style="width: var(--width-form)"`
   (420px) yazırdı; 390px-lik telefonda səhifə yana sürüşürdü.
   Qoşulma ekranı isə MƏHZ telefonda işlədilir. (`qosul` səhifəsi
   sonradan silindi, qayda qalır — `sessiya.html` də telefondadır.)
   → `.form-shell` (`width:100%` + `max-width`) və
   `TestMobileWidthDiscipline`.

3. **Geri bildirim yalnız hərfi göstərirdi.** «Düzgün cavab: B» —
   variantlar isə artıq ekranda deyildi. Tələbə B-nin nə olduğunu
   xatırlamalı idi, yəni səhv cavabdan öyrənmə İMKANI YOX idi.
   → `answer-feedback.js`, hər iki ekran (ev tapşırığı + canlı sessiya)
   üçün eyni mətn.

**Alət:** `deploy/diagnostics/`-dəki skriptlərə əlavə olaraq bu
sessiyada Playwright ilə üfüqi sürüşmə ölçüsü (`scrollWidth` vs
`clientWidth`) və mock API ilə DOLU məzmun render-i işlədildi.

**Xəbərdarlıq — mock real modeldən yazılmalıdır.** Bu sessiyada İKİ
dəfə mock-un özü səhv oldu və mövcud olmayan «bug» göstərdi: bir dəfə
ev tapşırığı statusları ingiliscə uydurulmuşdu (real API onsuz da
Azərbaycanca qaytarır), bir dəfə istifadəçi `name` sahəsi ilə
saxlanılmışdı (real `UserInfo` `display_name` işlədir). Mock məlumatı
HƏMİŞƏ `server/models.py`-dən yoxlanmalıdır.

## Dərs: statik fayllar `scp` ilə köçürüləndə nginx 403 verir (2026-09-10)

İlk veb deploy-da fayllar köçdü, `nginx -t` keçdi, API 200 qaytardı,
amma sayt **403** verdi. Səbəb: `scp` qovluğu `drwx------` (700) ilə
yaradır — `scp` root adından işləyir, `nginx` isə `www-data` kimi.
nginx qovluğa girə bilmir.

nginx xəta jurnalı bunu birbaşa deyirdi:
`"/opt/masterai-web/index.html" is forbidden (13: Permission denied)`

Həlli: `chmod -R a+rX /opt/masterai-web` — fayllara oxuma, YALNIZ
qovluqlara icra icazəsi (böyük `X` məhz bunu edir). `deploy_web.ps1`-ə
əlavə olundu.

**Bu hadisə deploy skriptinin healthcheck addımının dəyərini göstərdi:**
köçürmə uğurlu görünürdü, sınıqlığı yalnız canlı ünvandan yoxlama tapdı.

## Dərs: real material uğursuzluğu — Wikipedia `requests`-in defolt User-Agent-ini bloklayır

Flutter app-ın real emulyator (Android Studio AVD) testində qrup çatına
sayt linki (`az.wikipedia.org`) yükləndi, backend "Sayt yüklənmədi" ilə
uğursuz oldu. VPS-də birbaşa reproduksiya edildi:
`requests.get(url)` (heç bir header-siz) → **403**, eyni sorğu brauzer
`User-Agent`-i ilə → **200**. Kök səbəb: Wikimedia `python-requests/...`
kimi bot-görünüşlü UA-ları rədd edir. `pipeline/ingestion/web_extractor.py`-da
`_download_static()`-a sabit brauzer `User-Agent` header-i əlavə olundu
(test: `test_download_static_sends_browser_user_agent`, 264 test).
**Bu, "mənbədən yoxla" prinsipinin daha bir nümunəsidir** — pytest-in
mock-lanmış fixture-ları bunu görə bilməzdi, yalnız real bir saytla real
şəbəkə sorğusu tapdı. Eyni zamanda bu hadisə "Bilinən risklər"dəki
`_notify_admin_webhook()` sınağını da real təsdiqlədi (Telegram-a real
bildiriş gəldi).

## Dərs: Groq `llama-3.3-70b-versatile` modelini dayandırıb

Wikipedia fetch düzəlişindən (yuxarı bax) sonra material emalı yenə uğursuz
oldu, amma fərqli xəta ilə: "Kifayət qədər keyfiyyətli sual alınmadı
(0 < 3)". VPS-də birbaşa reproduksiya: `complete_with_fallback()` çağırışı
Groq-dan **404 model_not_found** aldı (`llama-3.3-70b-versatile` artıq
mövcud deyil), Ollama fallback-ı da VPS-də quraşdırılmadığı üçün (gözlənilən
— yalnız lokal) uğursuz oldu, `claude` provider-i isə heç konfiqurasiya
olunmayıb (`ANTHROPIC_API_KEY` yoxdur) — nəticədə bütün provider-lər
uğursuz oldu. `client.models.list()` ilə hesabın canlı model siyahısı
sorğulandı (sənəd yox, HƏQİQİ API cavabı) — `llama-3.3-70b-versatile`
siyahıda YOXDUR, Groq artıq əsasən `openai/gpt-oss-*`, `qwen/*` modellərini
saxlayır. `pipeline/providers.py`-də defolt `GROQ_MODEL`
`openai/gpt-oss-120b`-yə dəyişdirildi (`.env.example` də yeniləndi).
**Diqqət: `dildostu/server/dildostu_server/providers.py`-də də eyni
köhnəlmiş defolt var** (bu tapşırığın əhatəsindən kənar saxlanıldı, ayrıca
düzəldilməlidir). Bu, "mənbədən yoxla" prinsipinin daha bir nümunəsidir —
LLM provider-lərin model kataloqu vaxtaşırı dəyişir, kodda sabit yazılmış
model adı sükutla köhnəlib sınmaya bilər; pytest mock-ları bunu görə
bilməz, yalnız real API çağırışı aşkar edir.

## Dərs: Flutter app SDK-sız yazıldı, sonra istifadəçinin real mühitində sınandı

`app/` bu sandbox-da (Flutter SDK YOXDUR) yazılıb, sonra istifadəçinin
Windows mühitində (`flutter pub get`/`analyze`/`test`) REAL yoxlanıldı.
Özünü-nəzərdən keçirmədə (SDK-sız) 2 bug, real icrada isə 3 ƏLAVƏ bug
tapılıb düzəldilib — cəmi 5:

**SDK-sız özünü-nəzərdən keçirmədə tapılan (2):**
1. Dart string interpolasiyası: `'($resp.statusCode)'` `resp`-i
   `toString()`-lə çap edib sonra hərfi ".statusCode)" yazardı —
   property access `${}` tələb edir, bare `$` yalnız sadə
   identifikatorlar üçündür.
2. Quiz sual kartının "bağlıdır" statusu yalnız lokal tap-i izləyirdi —
   çat yenidən açılanda artıq nəticəsi gəlmiş (`QuizResultItem`) sual
   kartı hələ aktiv görünüb toxunanda backend-in `AlreadyAnswered`
   xətası alınırdı.

**İstifadəçinin real mühitində (`flutter pub get`/`analyze`/`test`) tapılan (3):**
3. **`flutter pub get`:** `flutter_secure_storage ^11` (`win32 ^6.0.1`)
   və `file_picker ^10.1.2` (`win32 ^5.9.0`) versiya toqquşması —
   `file_picker: ^12.2.0`-a yüksəldildi.
4. **`flutter analyze`:** `file_picker` 10→12 yüksəldilməsi API-ni
   dəyişmişdi — `FilePicker.platform` artıq YOXDUR, statik metodlar
   birbaşa `FilePicker`-dədir (`FilePicker.pickFile(...)`).
5. **`flutter test`:** iki ayrı problem —
   a) `Building native assets for package:objective_c failed` (boşluqlu
      Windows yolu hook script-ini qırır) — `dildostu/app/pubspec.yaml`-da
      ARTIQ HƏLL EDİLMİŞ eyni problem, eyni `dependency_overrides`
      (`path_provider_android: 2.2.23`, `path_provider_foundation: 2.4.4`)
      tətbiq edildi;
   b) `http.Response(String, int)` konstruktorunun `encoding` adlı
      parametri YOXDUR (mənim ilk düzəlişim — `encoding: utf8` — buna görə
      compile xətası verdi, istifadəçinin real paket mənbəyini
      göstərməsi ilə üzə çıxdı). Kodlaşdırma daxili olaraq `headers`-dəki
      `content-type`-dan törədilir: `application/json` olsa avtomatik
      utf8, əks halda (header göndərilməsə də) defolt **latin1** —
      Azərbaycan hərfli test fikstürləri (`'Əli'`) sükutla xəta atırdı,
      bu da client kodunun geniş `catch (_)`-i tərəfindən "şəbəkə xətası"
      kimi gizlənirdi. Doğru həlli: `http.Response(body, code, headers:
      {'content-type': 'application/json'})`.

**Vəziyyət:** `flutter analyze` — "No issues found!" (təsdiqlənib).
`flutter test` — **26 test, hamısı keçdi** (təsdiqlənib, düzəliş 5b-dən
sonra). İlk addım (yeni Flutter işi başlayanda) həmişə: `cd app &&
flutter pub get && flutter analyze && flutter test` (bax
`app/README.md`) — bu 5 bug SDK olmadan tapıla BİLMƏZDİ, "mənbədən
yoxla" prinsipinin canlı nümunəsidir (ilk səhv düzəliş də daxil
olmaqla — mən özüm yoxlamadan güman etdim, istifadəçinin real paket
mənbəyini göstərməsi ilə düzəldi).

## Dərs: veb host konsolunda CORS unudulmuşdu — backend HEÇ VAXT brauzerdən çağırılmamışdı

Faza 4-ün (Canlı Sinif Sessiyası, host konsolu) real brauzer testində
(`flutter run -d chrome`, istifadəçinin real Windows mühitində) giriş
formasında "Bağlantı xətası" alındı, baxmayaraq ki eyni backend mobil
tərəfdən (`flutter run` Android emulyator/cihaz) aylardır problemsiz
işləyir. Kök səbəb: `server/app.py`-də HEÇ VAXT `CORSMiddleware`
qurulmayıb — mobil HTTP client-i brauzerin same-origin siyasətinə tabe
deyil, ona görə bu problem indiyə qədər ÜZƏ ÇIXMAMIŞDI (bütün əvvəlki 341
test və real mobil test bunu görə bilməzdi). `localhost:...`-dan
`https://masterai.prdostu.com`-a `fetch`/`XMLHttpRequest` (Flutter
`http` paketinin veb tərəfi bunları işlədir) cross-origin sayılır,
server `Access-Control-Allow-Origin` header-i qaytarmadığı üçün brauzer
cavabı client koduna çatdırmır — bu da bizim `ApiException`-ın geniş
`catch (_)`-i tərəfindən "şəbəkə xətası" kimi göstərilir (eyni
gizlətmə naxışı `dildostu` UA-403 dərsində də olub).

Həll: `app.add_middleware(CORSMiddleware, allow_origins=["*"],
allow_credentials=False, allow_methods=["*"], allow_headers=["*"])`
əlavə edildi (`allow_credentials=False` MƏCBURİDİR —
`allow_origins=["*"]` ilə `True` uyğun gəlmir, üstəlik auth Bearer
header-lə aparılır, cookie/credential yoxdur, ona görə wildcard
təhlükəsizdir). Testlər: `TestCors` (`tests/server/test_app.py`) —
adi sorğuda `access-control-allow-origin: *` VƏ preflight (`OPTIONS` +
`Access-Control-Request-Method`) sorğusunun 200 qaytardığını yoxlayır
(343/343 test keçir). **Bu, "mənbədən yoxla" prinsipinin daha bir
nümunəsidir** — CORS SƏLƏHLƏNMƏSİ yalnız real brauzerdə, real
cross-origin sorğu ilə üzə çıxır, pytest-in `TestClient`-i (server
prosesinin daxilindən çağırdığı üçün) və mobil `flutter run` bunu
GÖRƏ BİLMƏZ. **Diqqət:** bu düzəliş hələ VPS-ə deploy EDİLMƏYİB
(`git pull` + `systemctl restart masterai` lazımdır) — deploy-dan sonra
Chrome-da yenidən sınanmalıdır.

## Qeyd

Ad seçimi ilə bağlı: repoda `masternr1/` (Master NR 1 tədris mərkəzi üçün AI
müştəri köməkçisi) mövcuddur — fərqli məhsuldur, adların oxşarlığına diqqət et.
