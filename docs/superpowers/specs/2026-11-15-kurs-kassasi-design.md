# Kurs Kassası: data sxemi və şagird itkisi (churn) hədəfi

**Tarix:** 2026-11-15
**Status:** Addım 1 (data sxemi, hədəf, sintetik generator) və addım 2 (Kassa paneli) hazırdır. Növbəti addımlar: sklearn modeli, feature engineering + PyTorch, qəbz oxuyucu (QLoRA), agentlər.
**Bazar araşdırması və plan:** https://claude.ai/artifact/QYJUZWQv4nF8Pg4gUoCg81

## Problem

Hazırlıq kursunun sahibi şagirdin getdiyini ödəniş gəlməyəndə bilir, yəni gec.
Hər gedən şagird ayda 60-150 AZN gəlir itkisidir. Məqsəd: hər ayın 1-də sahibə
«bu ay getmə riski yüksək olan şagirdlər» siyahısını vermək ki, zəng etsin.

## Data mənbələri (masterai-də artıq var)

Model YALNIZ masterai-nin mövcud cədvəllərindən öyrənir, yeni məlumat toplamırıq.
Sintetik generator da eyni sütun adları ilə yazır (`ml/churn/schema.py`), ona görə
sonra real bazadan oxuyan yükləyici eyni dataset kodunu işlədəcək.

| Cədvəl (masterai) | Sütunlar | Nə üçün |
|---|---|---|
| `chat_members` (qrup = sinif) | `chat_id`, `user_id`, `joined_at` | şagird nə vaxtdan kursdadır |
| `payment_fees` | `chat_id`, `student_id`, `monthly_amount` | aylıq haqq (AZN) |
| `payment_records` | `chat_id`, `student_id`, `month` (YYYY-AA), `amount`, `paid_at` | hansı ay nə vaxt ödənib |
| `lessons` | `id`, `chat_id`, `starts_at` | dərs cədvəli |
| `lesson_attendance` | `lesson_id`, `user_id`, `joined_at` | davamiyyət |
| `homework_assignments` | `id`, `chat_id`, `due_date` (+ sintetikdə `question_count`) | ev tapşırığı |
| `homework_attempts` | `assignment_id`, `student_id`, `score` (düzgün cavab sayı), `completed_at` | tapşırıq nəticəsi |

Bütün vaxtlar UTC ISO mətnidir (masterai-nin qaydası). `month` ödənişin hansı aya
aid olduğudur, `paid_at` isə pulun nə vaxt qeyd olunduğu: bunlar fərqlidir və
leakage-in əsas mənbəyidir (aşağıda).

## Hədəf (target)

**Kəsik (snapshot) tarixi `t`** = hər ayın 1-i, 00:00 UTC. Hər kəsik üçün hər
uyğun şagird bir sətirdir.

**Uyğun şagird** (`t` anında):
- `joined_at < t`;
- `t`-dən əvvəlki 45 gündə ən azı bir fəaliyyəti var (davamiyyət, tapşırıq və ya ödəniş).
  Artıq getmiş şagirdi təkrar-təkrar «getdi» saymırıq;
- kursun proqramı bu ay davam edir. Abituriyent qrupu iyunda imtahanla BİTİR: iyul
  və avqust kəsikləri bu qrup üçün atılır, çünki proqramın bitməsi itki deyil.

**Hədəf `churned = 1`**, əgər pəncərədə `[t, t + 30 gün)`:
- `month = ay(t)` üçün ödəniş YOXDUR (`paid_at < t + 30 gün`), **və**
- heç bir fəaliyyət yoxdur (dərs, tapşırıq).

**Borclu ≠ getmiş.** Dərsə gələn, amma ödəməyən şagird `churned = 0`-dır, panelin
ayrıca «borc» siyahısına düşür. Bu, maliyyə panelinin iki fərqli sualıdır:
«pulu gec gələcək» və «şagirdi itirəcəyik».

Niyə 30 gün: sahib ayda bir dəfə siyahıya baxıb zəng edir; daha qısa pəncərə gec
ödəyən sadiq şagirdləri səhvən «getdi» edər.

## Leakage qaydaları

1. **Əlamət yalnız `< t` hadisələrdən.** `ml/churn/dataset.py` hər cədvəli
   `t`-dən əvvələ kəsir, sonra əlamət hesablayır. Test: `t`-dən sonrakı bütün
   hadisələri silmək və ya qarışdırmaq əlamətləri DƏYİŞMƏMƏLİDİR.
2. **`month` deyil, `paid_at`.** Oktyabr ayının ödənişi noyabrın 10-da qeyd
   olunubsa, noyabrın 1-i kəsiyində o ödəniş HƏLƏ YOXDUR. `month`-a görə süzmək
   gələcəyi sızdırar. Test bunu ayrıca yoxlayır.
3. **Xatırlatma, «Ödədi» düyməsini basan müəllim (`marked_by`), müəllimin əl ilə
   qeydləri** əlamət deyil: bunlar çox vaxt itkinin özündən SONRA baş verir.
4. **Bölgü vaxta görədir**, təsadüfi yox: train = köhnə aylar, test = son aylar
   (addım 3-də). Eyni şagirdin fərqli ayları train/test-ə yayıla bilər, amma test
   ayı həmişə train aylarından sonradır.
5. **Sintetik «həqiqət» (`truth`)** (şagirdin gizli motivasiyası, getmə tarixi)
   yalnız generatorun yoxlanması üçündür, dataset kodu ona toxunmur.

## Sintetik generator (`ml/churn/synth.py`)

Real tarixçə hələ azdır, ona görə generator realistik naxışlarla data yaradır:

- 3 kurs proqramı: abituriyent (sentyabr-iyun, 120 AZN), magistr (sentyabr-may,
  90 AZN), ingilis dili (il boyu, 70 AZN). Rəqəmlər parametrdir.
- Hər şagirdin gizli **marağı** (engagement) var, həftədən həftəyə təsadüfi dəyişir.
  Davamiyyət, tapşırığı etmə və bal bu marağa bağlıdır.
- **Ödəniş vərdişi:** çoxu ayın ilk 5 günü, bəziləri həmişə gec, bir qismi borclu qalır.
- **Getmə riski** (ayda) maraq azaldıqca, gecikmə artdıqca və sezonda artır
  (yanvar: qış tətilindən sonra; mart: sınaq nəticələrindən sonra).
- Gedənlərin ~70%-ində 2-6 həftə əvvəldən siqnal var (davamiyyət və bal düşür),
  ~30%-i qəfil gedir: model hər şeyi tuta bilməməlidir, real həyat da belədir.
- Sentyabr-oktyabrda əsas qəbul, il boyu az sayda yeni şagird.
- `seed` eyni olduqda nəticə bayt-bayt eynidir.

Gözlənilən aylıq itki: 4-12% (Azərbaycan kursları üçün real rəqəm yoxdur,
pilotda Master NR 1 data-sı ilə yoxlanmalıdır).

## İlk nəticə (seed 7, 400 şagird)

2523 sətir, aylıq itki 2-13% (ümumi 8.6%), borclu qalıb davam edən 8.3%.
Orta dəyərlər: gedənlərdə son 30 gün davamiyyət 0.22, qalanlarda 0.67; son
fəaliyyətdən keçən gün 22 və 2.

Bilinməli iki xüsusiyyət:
- Ayın sonunda gedən şagird çox vaxt kəsikdən ƏVVƏL artıq susub. Ona görə
  `days_since_activity > 14` kimi sadə qayda güclü baza olacaq. Addım 3-də
  model bu qayda ilə müqayisə olunmalıdır: modelin dəyəri hələ aktiv, amma
  sönən şagirdləri tapmaqdadır.
- Pəncərənin içində gedən, amma əvvəlcə ödəyən və ya bir dərsə gələn şagird
  bu kəsikdə `0`-dır, növbəti ayın kəsiyində `1` olur. Bu, tərifin nəticəsidir,
  səhv deyil.

## İşə salma

```bash
python -m ml.churn --students 400 --seed 7 --out /tmp/kassa
# /tmp/kassa/*.csv (cədvəllər) + churn_dataset.csv (kəsik × şagird sətirləri)
```

## Addım 2: Kassa paneli

`web/kassa.html`, kurs rəhbəri (`is_admin`) üçün, bütün qruplar üzrə bir ay:

| Göstərici | Tərif |
|---|---|
| Gözlənilən | ay bitməzdən əvvəl qoşulmuş və aylıq məbləği olan hər (qrup, tələbə) cütünün məbləği |
| Yığılan | bu ay (`month`) üçün qeyd olunmuş ödənişlər; faiz = yığılan / gözlənilən |
| Borc | ödənməmiş cütlər: neçə gün gecikir (ayın 1-dən və ya qoşulma günündən), ardıcıl neçə ay, son ödəniş |
| Xalis | yığılan - xərclər (müəllim maaşı, icarə, reklam, kommunal, digər) |
| Trend | son 6 ay: gözlənilən, yığılan, xərc, xalis |

2+ ay ödəməyən tələbə «çox güman ki gedib» kimi qırmızı işarələnir: bu, churn
modelinin (addım 3) GEC versiyasıdır. Model eyni siyahını bir ay ƏVVƏL verməlidir.

API: `GET /live/kassa?month=`, `POST /live/kassa/expenses`,
`DELETE /live/kassa/expenses/{id}`, `POST /live/kassa/mark`, `POST /live/kassa/remind`.

## Açıq suallar

- Master NR 1-in anonim ödəniş cədvəli mümkündürmü? Olarsa, generatorun
  parametrlərini real paylanmaya uyğunlaşdıracağıq.
- Real masterai-də şagirdin kursdan rəsmi «çıxış» qeydi yoxdur. Gələcəkdə
  sahib panelində «çıxdı» düyməsi əlavə etsək, hədəf daha dəqiq olar.
