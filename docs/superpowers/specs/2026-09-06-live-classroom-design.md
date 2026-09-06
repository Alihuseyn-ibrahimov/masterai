# MasterAI — Canlı Sinif Sessiyası (Dizayn Sənədi)

**Tarix:** 2026-09-06
**Status:** Təsdiqlənib (istifadəçi tərəfindən brainstorm dialoqunda), implementasiya planına keçilir
**Əhatə dairəsi:** Master NR 1 Tədris Mərkəzinə satış üçün Faza-1 MVP —
müəllimin dərsdə idarə etdiyi, tələbələrin PIN kodla qeydiyyatsız
qoşulduğu, Kahoot-tərzi canlı sinif quiz-i.
**Mövcud MVP üzərinə YOX, ONUN YANINA qurulur** — hazırkı dostluq/qrup
çatı+asinxron quiz axını (`server/quiz_runner.py`, `chat_quiz_sessions`)
bir hərf belə dəyişmir. Yeni məhsul xətti tamam paralel infrastrukturdur,
yalnız AI sual-generasiya pipeline-ını (`pipeline/`) yenidən istifadə edir.

## 1. Problem və məqsəd

MasterAI-ın hazırkı MVP-si fərdi/dost-qrupu özünütəhsil aləti kimi
qurulub və real mühitdə (emulyator+fiziki cihaz) təsdiqlənib. İndi hədəf
fərqlidir: bunu Master NR 1 kimi tədris mərkəzlərinə **B2B məhsul** kimi
satmaq — müəllimin DƏRS ZAMANI, bütün sinifi eyni anda canlı bir quiz-ə
cəlb etdiyi alət. Master NR 1 kursu altı fənn tədris edir (məntiq,
informatika, dünyagörüşü, Azərbaycan dili, qanunvericilik, xarici dil) —
sual dəstləri bu fənlərə görə etiketlənməlidir.

Bu, mövcud "tələbə özü material yükləyib dostlarla asinxron həll edir"
axınından fərqlidir: burada müəllim tempi idarə edir, tələbələr isə
qeydiyyatsız, PIN kodla qoşulur (Kahoot/Quizizz modeli — dərsdə sıfır
sürtünmə).

**Faza-1 həll etmir (Faza-2+):** ev təkrarı rejimi (dərsdən sonra
asinxron həll — Faza-2), fərdi tələbə tarixçəsi (anonim iştirakçılar
üçün mümkün deyil, hesab sistemi tələb edər), sürət-bonuslu xallandırma,
çox-müəllimli hesab idarəetməsi, sual redaktə/təsdiq ekranı.

## 2. Arxitektura seçimi

Üç yanaşma qiymətləndirildi:

- **A) Yeni paralel "Canlı Sessiya" alt-sistemi (SEÇİLDİ)** — yeni DB
  cədvəlləri, yeni WS namespace, yeni Flutter ekranları. Yalnız
  `pipeline.generate_quiz()` yenidən istifadə olunur.
- **B) Mövcud `chat_quiz_sessions`/`ConnectionManager`-i genişləndirmək**
  — RƏDD EDİLDİ. PIN-lə qoşulan qeydiyyatsız iştirakçıları mövcud
  `users` cədvəlinə uyğunlaşdırmaq, artıq 263 testlə təsdiqlənmiş canlı
  sistemi (WS reyestri, quiz timeout-ları, `RLock`-lu Store-lar)
  destabilizasiya riskinə atardı.
- **C) Tam ayrı servis** — RƏDD EDİLDİ, əsassız təkrar iş (eyni VPS/komanda).

**Qərar:** A. Pilot metodologiyasının "bir proses dərin get, mövcudu
pozma" prinsipinə uyğun — mövcud MVP toxunulmaz qalır.

## 3. Verilənlər bazası modeli (yeni cədvəllər)

```
question_sets        — id, subject (enum: mentiq | informatika |
                        dunyagorusu | azerbaycan_dili | qanunvericilik |
                        xarici_dil), title, created_at,
                        material_source (mövcud `MaterialSource.kind`
                        dəyərləri: link/pdf/image)
question_set_items    — question_set_id, question_id (mövcud `questions`
                        cədvəlinə istinad — pipeline/sxem DƏYİŞMİR)
live_sessions         — id, question_set_id, pin (6 rəqəm, aktiv
                        sessiyalar arasında unikal), status
                        (waiting|active|finished), current_question_index,
                        created_at, report_json (nullable, bitəndə dolur)
live_participants     — id, session_id, display_name (sərbəst mətn,
                        istifadəçi hesabı YOXDUR), joined_at
live_answers          — participant_id, question_index, chosen_index,
                        is_correct, answered_at
```

**Niyə `question_sets` çatdan asılı deyil:** hazırkı material→sual axını
`materials.chat_id`-ə bağlıdır. Müəllim materialı dərsdən ƏVVƏL, heç bir
çat olmadan hazırlaya bilməlidir — ona görə `question_sets` müstəqil,
fənn-etiketli bir qatdır, `pipeline.generate_quiz()`-i birbaşa çağırır
(mövcud `server/app.py`-dəki `_process_material` naxışına bənzər fon
emalı, sadəcə nəticə bir çata yox, bir `question_set`-ə yazılır).

**Xallandırma:** sadə +1/düzgün cavab (mövcud `quiz_runner`-dəki
məntiqin eynisi, bax `server/quiz_runner.py:223-229`).

## 4. Backend axını — WebSocket protokolu

**Yeni endpoint-lər** (mövcud `/ws/chat/{id}` toxunulmur):

```
POST /live/sessions              — {question_set_id} → {session_id, pin}
                                    (müəssisə JWT-si ilə qorunur)
WS   /ws/live/{pin}/host          — müəllimin brauzeri (JWT ilə)
WS   /ws/live/{pin}/play          — tələbənin telefonu
                                    ({display_name} — token YOXDUR)
```

**Hadisə axını:**

1. Tələbə `pin`+`display_name` ilə `play` WS-inə qoşulur → backend
   `live_participants` yaradır → HOST-a "yeni iştirakçı" broadcast edir
2. Müəllim "Başla" düyməsinə basır → status=`active`, 1-ci sual həm
   host-a (böyük mətn+seçimlər), həm bütün `play`-lərə (A/B/C/D/E
   düymələri) broadcast olunur, server-idarəli geri sayım başlayır
   (defolt 20san — konfiqurasiya oluna bilər, sabit tələb deyil)
3. Hər cavab gələndə host ekranında "X/N cavab verdi" canlı yenilənir
   (kimin nə seçdiyi göstərilmir)
4. Vaxt bitəndə (ya hamısı cavablayanda) → düzgün cavab+izah hər iki
   tərəfə göstərilir, canlı liderlik lövhəsi (top 5) yenilənir
5. Müəllim "Növbəti sual" basır → 2-ci addıma qayıt
6. Son sualdan sonra → status=`finished`, yekun hesabat hazırlanır
   (bölmə 6)

**Timer server-tərəfli idarə olunur** (mövcud `_schedule_timeout`
naxışına bənzər `asyncio.create_task`+`app.state`-də referans saxlama,
bax `server/app.py` və quiz-orchestration dizaynındakı "arayışsız
`create_task` riskli praktikadır" qeydi) — müəllimin cihazının
gecikməsindən asılı olmasın deyə.

## 5. Frontend — iki yeni ekran ailəsi

**A) Host konsolu (Flutter WEB build, noutbukda brauzerdə, proyektora
HDMI ilə):**
- "Sessiya hazırla" — fənn seç → mövcud `question_sets`-dən seç (ya yeni
  material yüklə)
- "Gözləmə otağı" — İRİ PIN + QR kod (telefonla skan edib avtomatik
  qoşulmaq üçün) + canlı qoşulan adlar siyahısı + "Başla"
- "Canlı sessiya" — böyük sual+seçimlər, "X/N cavab verdi" sayğacı,
  "Növbəti sual"/"Bitir"
- "Yekun liderlik lövhəsi + hesabat" (bölmə 6)

Flutter web build artıq mövcuddur və real mühitdə sınanıb (`flutter run
-d chrome`). `file_picker`-in veb məhdudiyyəti (bax
`app/README.md`/`CLAUDE.md`) burada problem yaratmır — host konsolu fayl
seçmir, yalnız mövcud `question_sets`-dən seçir.

**B) Tələbə tərəfi (mövcud mobil app-a yeni giriş nöqtəsi, login
ekranından ƏVVƏL):**
- "Sinif sessiyasına qoşul" düyməsi — heç bir hesab tələb etmir
- PIN+ad → gözləmə ekranı ("müəllim başlamasını gözləyin")
- Sual gələndə: böyük A/B/C/D/E düymələri + geri sayım zolağı
- Cavabdan sonra: "Düzgün!/Səhv" + öz sırası (anonim, yalnız özünə
  görünür)

## 6. Sessiya sonu hesabatı (satış üçün əsas dəyər təklifi)

Sessiya bitəndə backend `live_answers`-dan hesablayır, host ekranında
göstərir və `live_sessions.report_json`-a yazır:

- **Yekun sıralama** — ad, düzgün cavab sayı, sıra
- **Sual-sual təhlil** — hər sual üçün "N nəfərdən M-i düzgün
  cavablandı" + ən çox seçilən səhv variant (bu, "sinif harada
  çətinlik çəkir" sualına cavab verir — institusional satış arqumenti)
- **Müəllim tərəfi:** host konsolunda "Keçmiş sessiyalar" siyahısı —
  hər sessiya sonradan yenidən açıla bilər

## 7. Faza-1 qərarları (istifadəçi ilə razılaşdırılıb)

| Mövzu | Qərar |
|---|---|
| İlk MVP rejimi | Canlı Kahoot-tərzi (ev təkrarı Faza-2-yə) |
| Tələbə qoşulması | PIN kod, qeydiyyatsız |
| Proyektor cihazı | Noutbuk/brauzer (Flutter web) |
| Müəllim hesabı | Tək paylanılan müəssisə hesabı |
| Nəticə hesabatı | Bəli, Faza-1-ə daxildir |
| Sual keyfiyyət nəzarəti | Yox — AI-nın yaratdığı suallar avtomatik istifadə olunur |

## 8. Əhatə xarici (Faza-2+)

- Ev təkrarı/asinxron rejim (dərsdən sonra)
- Fərdi tələbə tarixçəsi (anonim iştirakçılar üçün mümkün deyil)
- Sürət-bonuslu xallandırma (Kahoot-un öz modeli)
- Çox-müəllimli hesab idarəetməsi (rol sistemi)
- Sual redaktə/təsdiq ekranı (müəllim dərsdən əvvəl sualları gözdən
  keçirib silə bilsin)
- JS-rendering tələb edən saytlar üçün chromedriver (mövcud bilinən
  məhdudiyyət, bu dizaynın əhatəsində deyil)
