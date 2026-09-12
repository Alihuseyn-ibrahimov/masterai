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
