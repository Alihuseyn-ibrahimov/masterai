# Kurs Kassası: data sxemi və şagird itkisi (churn) hədəfi

**Tarix:** 2026-11-15
**Status:** Addım 1 (data sxemi, hədəf, sintetik generator) addım 2 (Kassa paneli), addım 3 (sklearn modeli), addım 4 (trend əlamətləri + PyTorch), addım 5 (qəbz oxuyucusu), addım 6 (agentlər + qoruyucu qat) və addım 7 (vahid eval) hazırdır. Növbəti: pilot və təqdimat (addım 8).
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

## Addım 5: qəbz oxuyucusu - QLoRA + vLLM (5-ci ay #35, #38)

Valideyn pulu atanda rəhbərə bank SMS-i, kağız qəbz və ya «Ayselin noyabr pulunu
köçürdüm» mesajı gəlir. Rəhbər onu Kassada «Qəbzi oxu»ya yapışdırır: məbləğ,
tarix, ödəyən, kartın son 4 rəqəmi, ay və şagird çıxır, şagird qeydiyyatdan
tapılır (ad + ödəyənin soyadı), rəhbər «Ödədi kimi qeyd et» basır. **AI heç nə
yazmır**: nəticə təklifdir, qeydi mövcud `/live/kassa/mark` edir. Həmin ay artıq
ödənibsə və ya qəbzdəki məbləğ aylıq məbləğdən fərqlidirsə rəhbər bunu görür.

**Data sintetikdir** (`ml/receipts/synth.py`, real qəbz şəxsi məlumatdır): 6 mətn
növü. `bank_sms` (balans çaşdırıcıdır), `card2card`, `cash_receipt` (OCR səhvləri),
`parent_message` (yiyəlik hal: «Lalənin» → «Lalə»), `ewallet` (komissiya
çaşdırıcıdır, ad maskalıdır), `messenger` («Uşaq:», «Ana:», «... ilə bitir»).
Son ikisi öyrətməyə DÜŞMÜR (`HELD_OUT`): model görmədiyi formatda ümumiləşirmi?

**Qaydalı baza** (`pipeline/receipt_reader.py::rule_based`, LLM-siz ehtiyat yol):

| Test dəsti | Hamısı düz | amount | date | payer | card | month | student |
|---|---|---|---|---|---|---|---|
| Görülən 4 növ (160) | 91% | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.91 |
| Görülməyən 2 növ (800) | 50% | 1.00 | 1.00 | 0.76 | 0.74 | 1.00 | 0.50 |

Qaydalar şablona yazılıb: `ewallet`-də 100%, `messenger`-də 0% (şagirdi tapmır).
Görülən növlərdə qalan səhv yiyəlik haldır: «Kamranın» həm «Kamran+ın», həm
«Kamra+nın» ola bilər, qayda adları bilmədən ayıra bilmir. QLoRA modelinin
üstünlüyü məhz bu iki yerdə ölçülür.

**Uydurmaya qarşı (`grounded`):** LLM-in məbləği mətndə yoxdursa bütün cavab atılır
(pul məsələsində təxmin yoxdur) və qaydalara düşülür; tarix, kart, ad, ay mətndə
tapılmırsa yalnız o sahə `null` olur və rəhbərə «atıldı» deyilir. Sintetik datanın
bütün düzgün etiketləri bu yoxlamadan keçir (test var).

**Məxfilik:** qəbzdə ad və kart rəqəmi var. Defolt olaraq YALNIZ öz vLLM serverimiz
çağırılır (`VLLM_BASE_URL` + `VLLM_RECEIPT_MODEL`); Groq/Claude yalnız
`RECEIPT_ALLOW_EXTERNAL_LLM=true` ilə. Heç biri yoxdursa qaydalar işləyir.

**QLoRA + vLLM** (`ml/qlora_receipts.ipynb`, Colab T4): Qwen2.5-1.5B-Instruct NF4 +
LoRA r=16, dataset Colab-da `python -m ml.receipts.sft` ilə yaranır (sistem və
istifadəçi mesajı produksiya ilə bayt-bayt eynidir). Müqayisə: qaydalar, baza,
QLoRA, görülən və görülməyən növlərdə. Sonra vLLM **multi-LoRA**
(`--enable-lora --lora-modules receipts=...`: bir baza model, bir neçə adapter;
gələcəkdə `masterai-mcq` ilə eyni GPU), **`guided_json`** (dekodlaşdırma
`Receipt` sxeminə bağlanır: JSON oxunma 100% olmalıdır, sual məzmundur) və
`ml/bench_llm.py` ilə gecikmə. Notebook burada İŞLƏDİLMƏYİB (GPU yoxdur):
QLoRA nəticəsi Colab-da alınmalıdır.

## Addım 6: Kassa agentləri - CrewAI + AutoGen + guardrails (5-ci ay #36, #39, #40)

`kassa_agents/`, rəhbərin kompüterində işləyir (CrewAI və AutoGen serverə QOYULMUR,
ikisi də ayrı venv-dədir: protobuf toqquşması). Data mövcud `GET /live/kassa` ilə
rəhbərin öz tokeni ilə gəlir (`teacher_mcp.MasterAIClient`), agentlər heç nə YAZMIR.

```
python -m kassa_agents.cli report --month 2026-11 --out kassa.md   # CrewAI
python -m kassa_agents.cli ask "Hansı qrupda borc ən çoxdur?"      # AutoGen
```

**Aylıq hesabat (CrewAI, `report_crew.py`):** Maliyyə analitiki → Risk analitiki →
Hesabat redaktoru, ardıcıl proses, LLM bizim fallback zəncirimizdir (`MasterAILLM`).
Nəticə üç bölmədir: Pul, Risk, Bu həftə (3 konkret addım).

**Kassaya sual (AutoGen, `sql_team.py`):** SQL analitiki `run_sql` aləti ilə
Kassanın yaddaşdakı ANONİM surətinə sorğu yazır, Yoxlayıcı cavabı alətin nəticəsi
ilə tutuşdurub «YEKUN» ilə bitirir. LLM rəqəmi «təxmin» etmir, cədvəldən oxuyur.

**Qoruyucu qat (`facts.py`, stdlib, CI-da sınanır):**

| Risk | Qayda |
|---|---|
| Şagird adı kənar LLM-ə gedir | `anonymize`: borclular «Şagird N», `student_id` və xərc qeydi atılır; sualdakı real ad da ləqəbə çevrilir (`alias_names`), ad yalnız rəhbərin kompüterində qaytarılır (`deanonymize`) |
| Agent rəqəm uydurur | `ground_report`: xülasədə (hesabat) və ya alət nəticəsində (sual) olmayan rəqəm daşıyan cümlə atılır, rəhbər atılan cümlələrin sayını görür. «1 200» = «1200», faiz və saylar (borclu sayı, yığım faizi) icazəlidir |
| SQL ilə yazma, fayl, sonsuz sorğu | `safe_query`: yalnız bir SELECT/WITH, sqlite authorizer yalnız oxumağa icazə verir (ATTACH, PRAGMA, load_extension, DML rədd), addım limiti sonsuz rekursiyanı kəsir, 200 sətir. Baza onsuz da yaddaşda surətdir |
| Prompt injection | `pipeline.guardrails.check_input` (tutor ilə eyni): injection LLM-dən ƏVVƏL bloklanır, telefon/kart maskalanır |

**Sınaq:** qoruyucu qat 17 testlə (CI), CrewAI komandası saxta LLM ilə (real CrewAI,
LLM real adı görmür, uydurulmuş proqnoz atılır), AutoGen komandası
`ReplayChatCompletionClient` ilə (real AutoGen: alət çağırışı, `DELETE` rədd, injection
blok, modelə gedən heç bir mesajda real ad yoxdur). Real modellə hələ işlədilməyib.

## Addım 7: vahid eval hesabatı (5-ci ay #33)

`python -m evals.kassa [--live] [--out kassa.md]`: şagird itkisi, qəbz oxuyucusu,
agentlərin qoruyucu qatı və (`--live`) agentlərin özü bir hesabatda, hər biri öz
bazası ilə. Offline hədlər `KASSA_GATES`-dədir, `tests/test_kassa_eval.py` CI-da qoruyur.
Ətraflı: `evals/README.md`.

Offline nəticə (seed 7/11, sintetik):

| Hissə | Nəticə |
|---|---|
| Zəng siyahısı | yalnız qayda: ayda 21 zəng, 96% dəqiq, gedənlərin 75%-i; qayda + model: 35 zəng, 69%, 87% (model «ən çox susan»dan yaxşı DEYİL) |
| Qəbz (qaydalar) | görülən növlər 92%, görülməyən 50% |
| Qoruyucu qat | 18/18 rəqəm qərarı, 11/11 hücum SQL, 5/5 injection, 0 səhv blok, 0 ad sızması |

**Eval bir səhv tapdı:** «Gələn ay yığım 3800 AZN olacaq» keçirdi (3800 xülasədə avqustun
gözləntisidir). Rəqəmli proqnoz cümləsi artıq atılır. Live nəticə (real LLM, QLoRA) hələ YOXDUR:
serverdə/Colab-da `--live` ilə alınmalıdır.

## Açıq suallar

- Master NR 1-in anonim ödəniş cədvəli mümkündürmü? Olarsa, generatorun
  parametrlərini real paylanmaya uyğunlaşdıracağıq.
- Qəbz oxuyucusu: real bank SMS-lərinin formatı (anonimləşdirilmiş 20-30 nümunə)
  sintetik ailələri yoxlamaq üçün kifayətdir.
- Real masterai-də şagirdin kursdan rəsmi «çıxış» qeydi yoxdur. Gələcəkdə
  sahib panelində «çıxdı» düyməsi əlavə etsək, hədəf daha dəqiq olar.
