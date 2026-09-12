# Quiz UX yenilənməsi — «əsl tədris tətbiqi» hissi

**Tarix:** 2026-09-12
**Səbəb (istifadəçinin sözləri):** «saytımız əsl education app abu havası
vermir», quizlər «maraqlı rəngarəng» olsun, sayt «AI ilə hazırlanmış kimi
görünməsin».

## Diaqnoz — üç ayrı səbəb, ikisi ölçüləbilən

**1. Quiz ekranı dizayn olunmuş komponenti İŞLƏTMİRDİ.**
`live-play-screen.js` və `tapsiriq.html` cavab variantlarını
`btn btn--secondary btn--block` + sətiriçi `justify-content: flex-start`
hack-i ilə çəkirdi. Nəticə: ekranda beş **bərabər boz düymə**.
`components.css`-də `.option` anatomiyası (hərf nişanı, nəticə işarəsi,
56px toxunma hədəfi) onsuz da var idi və **yalnız açılış səhifəsindəki
nümunə sualda** işlədilirdi. Yəni məhsulun ən vacib ekranı ən zəif
görünürdü.

**2. Palitra AI-nın standart görünüşü idi.**
`--color-bg: #FAFAF8` (isti krem) + Source Serif başlıq. Bu kombinasiya
(krem fon + nəşr serifi + isti aksent) hazırda AI-nın ən çox istehsal
etdiyi estetikadır. Üstəlik oxunuş assosiasiyası «hüquq bürosu /
jurnal»dır, «tədris tətbiqi» deyil.

**3. Fənn rəngləri istifadəsiz qalırdı.**
Altı fənn aksenti (`--subject-*`) var idi, amma yalnız kartın 3px sol
kənarında görünürdü. Məhsulun yeganə real rəng kimliyi işə salınmamışdı.

## Qərarlar

| Sahə | Əvvəl | İndi | Səbəb |
|---|---|---|---|
| Fon | `#FAFAF8` isti krem | `#F3F5FA` sərin qrafit | krem+serif AI imzasıdır |
| Başlıq şrifti | Source Serif 4 | **Archivo** (dəyişən, 100-900) | qrotesk qrafika rəqəmləri və enerjini daşıyır |
| Sənəd şrifti | — | Source Serif 4 `--font-document` kimi QALIR | hüquqi/sənəd səhifələrində yeri var |
| Cavab variantı | boz düymə | `.option` + A-E üçün **beş rəngli hərf nişanı** | göz variantları dərhal ayırır |
| Tərəqqi | faiz zolağı | **seqment** (sual-sual) | «7-dən 5-ini bitirdin» faizdən faydalıdır |
| Nəticə | kiçik nişan | **`.verdict`** bloku + ikon | düzgün/səhv hissi ötürülür |
| Motivasiya | yox | **`.streak`** (2+ ardıcıl) | tədris tətbiqlərinin ən güclü elementi |
| Yekun xal | mətn | **`.score-ring`** (`conic-gradient`) | kitabxanasız, «build addımı yoxdur» qorunur |
| Sıralama | `row row--between` | **`.rank`** + ilk üç yer nişanı | sıralamanın mənası ilk üçdədir |

## Rəng intizamı — əvvəlki qərarla ziddiyyət DEYİL

`tokens.css`-də «fənn rəngi düymə rəngi kimi İŞLƏDİLMİR» qaydası var idi
və **qalır**. Rəng yalnız MƏZMUNU işarələyir: hərf nişanı, tərəqqi
seqmenti, nəticə vəziyyəti. Səhifə karkası (fon, kart, düymə) sakit
qalır. Alabəzək tətbiq rəngin çoxluğundan deyil, rəngin MƏNASIZ yerdə
işlədilməsindən yaranır.

**Qırmızı və yaşıl variant rəngi kimi İŞLƏDİLMİR** — onlar
«səhv»/«düzgün» siqnallarıdır (bax aşağı, render-də tapılan qüsur).

## Paylaşılan modul: `assets/js/quiz-options.js`

Variant çəkilişi hər iki ekranda EYNİ moduldan gəlir. Bu, layihədə artıq
bir dəfə bahalı olan səhvin təkrarının qarşısını alır: geri bildirim
mətni iki ekranda ayrı yazılmışdı və düzəliş də iki yerdə edilməli oldu
(bax `answer-feedback.js` modul qeydi).

## Şrift seçimi MƏNBƏDƏN yoxlanıldı

Üç namizədin `cmap` cədvəli oxundu (sənədə yox, şrift faylının özünə):

| Şrift | Azərbaycan hərfləri |
|---|---|
| Archivo | **14/14 ✓** |
| Plus Jakarta Sans | 14/14 ✓ |
| Figtree | **12/14 — `Ə` və `ə` YOXDUR** |

Figtree ilk baxışdan uyğun görünürdü. Bu yoxlama məcburidir: əvvəl
Manrope da məhz `Ə` olmadığı üçün rədd edilmişdi.

## Brauzer render-i ÜÇ qüsur tapdı (kod testləri tuta bilməzdi)

1. **Xal dairəsində faiz mətni halqanın üstünə düşürdü** — dairənin
   mərkəzindən aşağıda enişən sahə daralır. Mətn dairənin altına çıxarıldı.
2. **D variantının rəngi qırmızı idi** — cavab verilməzdən ƏVVƏL D
   «təhlükəli» görünürdü, yəni rəng semantikası ilə toqquşurdu. Fuksiyaya
   dəyişdirildi.
3. **Açılış səhifəsində hərf nişanı görünməz olardı** — `.option__letter`
   fon üçün `--opt`, mətn üçün ağ işlədir; `--opt` təyin olunmasa boz fon
   üzərində ağ hərf alınır. Fallback rəngli edildi və açılış səhifəsinin
   nümunə variantlarına da rənglər verildi.

Əlavə olaraq geniş ekranda sətir uzunluğu düzəldildi (`.quiz-shell`,
`--width-prose`).

## Mövcud testlər üç səhvimi tutdu

Layihənin intizamı işlədi — bunlar düzəlişdən əvvəl commit edilə bilməzdi:

- `✓`/`✗` simvolları: **emoji ikon kimi işlədilə bilməz** (sprite var,
  `i-x` simvolu əlavə edildi)
- uzun tire (`—`) veb fayllarında qadağandır
- `--opt`/`--quiz-accent`/`--pct` tokenləri: komponent parametrləri kimi
  testin yerli siyahısına yazıldı (`--subject`/`--progress` ilə eyni)

## Yoxlama

- 1190 pytest + 183 Node testi keçir
- Chromium render: masaüstü/mobil, işıq/tünd — üfüqi sürüşmə YOXDUR,
  JS xətası YOXDUR
- **HƏLƏ EDİLMƏYİB:** real cihazda insan gözü ilə təsdiq və deploy


---

# İkinci iterasiya: yaşıl + sarı + qara

**İstifadəçi qərarı:** «əsas rənglərimiz yaşıl sarı və qara olsun».

## İki semantik toqquşma və həlli

Yaşıl artıq «düzgün», sarı artıq «xəbərdarlıq» demək idi. Brend rəngləri
onların üstünə gəlsəydi, istifadəçi siqnalları ayıra bilməzdi. Rollar
yenidən bölüşdürüldü:

| Rəng | Rolu | Nə DEYİL |
|---|---|---|
| Qara/qrafit | struktur, üst zolaq, mətn, «gözləyir» vəziyyəti | — |
| Adaçayı yaşıl | brend + əsas əməliyyat | «düzgün» onun DOYMUŞ variantıdır, ayrı yaşıl deyil |
| Sarı | enerji: ardıcıllıq, xal dairəsi, birinci yer | xəbərdarlıq DEYİL |
| Narıncı | YALNIZ xəbərdarlıq | sarıdan qəsdən ayrılıb |
| Qırmızı | YALNIZ səhv | — |

**«Seçildi, nəticə gözlənilir» vəziyyəti RƏNGSİZ edildi.** Əvvəl brend
rəngi ilə dolurdu; brend mavi olanda bu işləyirdi, yaşıl olandan sonra
«seçilmiş» ilə «düzgün» eyni ailədən iki solğun yaşıl olardı və tələbə
bir anlıq cavabın düzgün sayıldığını zənn edərdi.

**Mavi tamamilə getdi:** `info` statusu da qrafitə çevrildi,
`theme-color` metaları (17 səhifə) və favicon yeniləndi.

## Qara üst zolaq — «sinif lövhəsi»

Üst zolaq qaradır, cari səhifə isə **sarı** ilə işarələnir (təbaşir
naxışı). Funksional faydası: tətbiqin karkası məzmundan aydın ayrılır,
ağ sual kartları lövhənin üstündə oturur.

**Tünd rejimdə məntiq tərsinədir:** fon onsuz da qaradır, ona görə zolaq
fondan bir qədər AÇIQDIR. İlk dəyər (#0A0C08) fonla qaynayıb itirdi —
brauzer render-ində göründü.

## Variant rəngləri yenidən köklənib

Əvvəlki parlaq tonlar (indiqo, firuzə, fuksiya) yeni kimliklə yad dəst
kimi oxunurdu. İndi hamısı dərin torpaq tonlarıdır: slate-göy, firuzə-
yaşıl, tunc, gavalı, qrafit. Render-də A və E demək olar eyni görünürdü
(hər ikisi tünd bənövşəyi) — E qrafitə çevrildi, qara onsuz da brendin
rəngidir.

## Kontrast MƏNBƏDƏN yoxlanıldı

22 rəng cütünün WCAG nisbəti hesablandı (gözlə qiymətləndirilmədi):
**hamısı AA (4.5:1) keçir** — düymə, link, qara zolaq mətni, sarı nişan,
hər beş variant nişanı, işıq və tünd rejim ayrı-ayrı.

## Test qaydası yenə tutdu

Qara zolağın örtük rəngləri `rgba()` ilə yazılmışdı — `tokens.css`-dən
kənarda birbaşa rəng qadağandır. `--color-ink-hover`/`--color-ink-active`
tokenləri əlavə edildi (şəffaf ağ, yəni səth rəngi dəyişsə örtük də
dəyişir).
