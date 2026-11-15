# Kurs Kassası: data sxemi və şagird itkisi (churn) hədəfi

**Tarix:** 2026-11-15
**Status:** Addım 1 (data sxemi, hədəf, sintetik generator) addım 2 (Kassa paneli), addım 3 (sklearn modeli) və addım 4 (trend əlamətləri + PyTorch) hazırdır. Növbəti addımlar: feature engineering + PyTorch, qəbz oxuyucu (QLoRA), agentlər.
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

## Addım 3: sklearn modeli və sadə qayda (6-cı ay #43)

`python -m ml.churn.train --students 800 --seed 7`. Train: 2025-10..2026-02
(2899 sətir, itki 7.5%), test: 2026-03..2026-06 (2205 sətir, itki 10.3%).
`C` train daxilində son 3 ayın hər biri üçün «ondan əvvəlki aylarda öyrən, bu
ayda ölç» ilə seçildi (C = 0.1). Test aylarına seçimdə baxılmır.

| Model | ROC-AUC | PR-AUC | Ayın top-10%-i: dəqiqlik | top-10%: gedənlərin | Hələ aktivlər arasında AUC |
|---|---|---|---|---|---|
| Qayda: son fəaliyyətdən keçən gün | 0.954 | 0.876 | 0.79 | 78% | 0.849 |
| LogisticRegression | **0.960** | 0.875 | 0.79 | 78% | **0.871** |
| RandomForest | 0.956 | **0.879** | 0.79 | 78% | 0.858 |
| HistGradientBoosting | 0.954 | 0.868 | 0.77 | 76% | 0.852 |

**Zəng siyahısı** (test ayları, sahib hər ayın 1-də zəng edir):

| Siyahı | Ayda zəng | Dəqiqlik | Tapılan gedənlər |
|---|---|---|---|
| Yalnız qayda (14+ gün susub) | 44.5 | 0.91 | 162 / 228 (71%) |
| Qayda + aktivlərin ən çox susan 5%-i | 72.2 | 0.67 | **195 / 228 (86%)** |
| Qayda + modelin aktivlər üzrə ən riskli 5%-i | 72.2 | 0.66 | 192 / 228 (84%) |

**Nəticə (dürüst):** bu sintetik datada sklearn modeli sadə «neçə gündür susub»
sıralamasını ÜSTƏLƏMİR. LogReg əmsallarında da `days_since_activity` digərlərindən
4-5 dəfə güclüdür (+2.23; sonra keçən ayın davamiyyəti -0.49, ödəniş gecikməsi
+0.46). Üç seed-də (3, 7, 11) eyni mənzərə: model qaydadan 2-3 gedən az tapır.

Bunun iki səbəbi var: (1) generatorda gedənlərin çoxu kəsikdən əvvəl susur, yəni
siqnal demək olar tək əlamətdədir; (2) indiki 9 əlamət «son 30 gün» kəsikləridir,
trendi (davamiyyət NECƏ düşür) birbaşa görmür. Növbəti addım (#44 feature
engineering + PyTorch) məhz buna baxır: trend, ardıcıl buraxılan dərslər, balın
düşməsi, ödəniş gecikməsinin artması. Hədəf «qayda + günlər» siyahısının 86%-ni
eyni zəng sayı ilə keçməkdir. Keçə bilməsək, pilotda qayda + günlər qalır: bu da
nəticədir. Real Master NR 1 datasında mənzərə fərqli ola bilər.

Model `churn_model.json`-a çıxarılır (orta, miqyas, əmsal), server onu sklearn-siz
hesablayır (`ml/churn/model.py`). Kassa panelinə hələ qoşulmayıb: əvvəl modelin
qaydadan üstün olduğu göstərilməlidir, sonra real cədvəllərdən əlamət yığan
yükləyici lazımdır.

## Addım 4: feature engineering (#44) + PyTorch (5-ci ay #34)

`python -m ml.churn.deep --students 800 --seed 7`. Addım 3-ün bölgüsü və zəng
büdcəsi eynidir (qayda + ayda ~28 əlavə zəng).

**Yeni əlamətlər** (`dataset.ENGINEERED`, hamısı `cut`-dan sonra, test var):
davamiyyət trendi, 14 günlük davamiyyət, ardıcıl buraxılan dərslər, son dərsdən
və son tapşırıqdan keçən gün (ödəniş fəaliyyət sayılmır), tapşırıq və bal
trendi, 14 günlük hadisə sayı və onun əvvəlki 14 günə nisbəti, son 3 ayda gec
ödənən aylar, ödəniş gecikməsinin trendi. **GRU** üçün son 6 tam ayın aylıq
sırası (`ml/churn/sequence.py`: kursda idimi, davamiyyət, tapşırıq, bal, ödədimi,
gecikmə). PyTorch modellərində erkən dayanma train-in son ayındadır.

| Model (seed 7) | ROC-AUC | PR-AUC | Hələ aktivlər arasında AUC | Zəng siyahısı tapdı |
|---|---|---|---|---|
| Qayda: neçə gündür susub | 0.954 | 0.876 | 0.849 | **195 / 228 (86%)** |
| LogReg, 9 əsas əlamət | 0.960 | 0.875 | 0.871 | 192 (84%) |
| LogReg, + 11 trend əlaməti | 0.956 | 0.869 | 0.859 | 190 (83%) |
| MLP (PyTorch), 20 əlamət | 0.955 | 0.866 | 0.855 | 189 (83%) |
| GRU (PyTorch), 6 aylıq sıra | **0.961** | **0.880** | **0.873** | 193 (85%) |

Seed 11 və 3-də də eyni: zəng siyahısında qayda 90% və 88%, ən yaxşı model
88% və 86%. **Trend əlamətləri kömək etmədi**, LogReg-də bir az pisləşdirdi
(20 əlamət, ~220 gedən: artıq əlamət səs-küy öyrədir).

**Niyə: qaçırılan gedənlərə baxdıq** (yalnız analiz üçün sintetik `truth`-dan,
model ona baxmır). Seed 7-də siyahının qaçırdığı 33 gedəndən 19-u kəsikdən
ƏVVƏLKİ 14 gündə artıq getmişdi (az susduğu üçün qaydaya düşmədi), 14-ü
pəncərənin ilk 14 günündə getdi, 8-i «qəfil» idi (generatorda qəsdən siqnalsız).
Seed 11 və 3-də nisbət eynidir. Yəni qalan səhvlərin çoxu proqnoz problemi
deyil, **gec yoxlama** problemidir.

**Məhsul nəticəsi:** sintetik datada model yox, qayda qalır: «7+ gündür susan»
siyahısını ayda bir yox, **həftədə bir** vermək, yəqin ki, daha çox gedəni
tutar. Bu, hipotezdir: real Master NR 1 datasında yoxlanmalıdır. Model kodu
hazırdır, real datada qaydanı keçərsə Kassaya qoşularıq.

## Açıq suallar

- Master NR 1-in anonim ödəniş cədvəli mümkündürmü? Olarsa, generatorun
  parametrlərini real paylanmaya uyğunlaşdıracağıq.
- Real masterai-də şagirdin kursdan rəsmi «çıxış» qeydi yoxdur. Gələcəkdə
  sahib panelində «çıxdı» düyməsi əlavə etsək, hədəf daha dəqiq olar.
