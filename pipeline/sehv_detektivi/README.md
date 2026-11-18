# Səhv Detektivi (masterai inteqrasiyası)

Şagirdin addım-addım həllində **ilk səhv addımı** və **səhvin növünü** tapır: riyaziyyat
(8 növ: kəsr, işarə, əməl ardıcıllığı, faiz, tərəf keçirmə, hesab, ixtisar, paylama) və
məntiq testləri (6 növ: ardıcıllıq qaydası, «bəzi/hamısı», tərs nəticə, inkar, şərt, sayma).

Model: `Qwen/Qwen2.5-1.5B-Instruct` + QLoRA adapteri (v3), ayrı repoda öyrədilib
(`sehv-detektivi`: data generatorları, golden dəst, notebook-lar, kalibrasiya). Bura yalnız
inferens üçün lazım olanlar köçürülüb: `taxonomy.py`, `prompts.py` (təlimlə bayt-bayt eyni,
test hash ilə yoxlayır), `schema.py`, `sympy_check.py`.

## Marşrutlar

- `GET /me/diagnose` - səhv növləri + model qoşulubmu.
- `POST /me/diagnose` - `{"domain": "riyaziyyat"|"mentiq", "problem": "...", "steps": [...]}`
  və ya `"solution": "hər sətir bir addım"`. «1)», «2.» nömrələri atılır. 10 dəqiqədə 30 yoxlama.
  Heç nə saxlanmır.

Cavab: `status` (`error_found` | `correct` | `unknown`), `wrong_step`, `error_type`,
`error_name`, `explanation`, `steps[]` (`ok` / `wrong` / `after_error`), `source`, `sympy_checked`,
`agreement`, `model_error`.

Veb: `web/sehv.html` («Həllimi yoxla», AI tutor səhifəsindən link).

## Qərar necə verilir

1. Model varsa JSON diaqnoz verir.
2. `SEHV_NULL_THRESHOLD` qoyulubsa və backend «düzgündür» ehtimalını (`p_null`) hesablaya bilirsə,
   `p_null >= eşik` → «düzgündür».
3. sympy riyazi zənciri (kəsr, ifadə, tənlik) oxuya bilirsə onun qərarı üstündür. Golden-də 46/100
   nümunəni oxuyur və heç birində etiketə zidd getmir (`tests/test_sehv_detektivi.py`).
4. Model yoxdursa və ya düşübsə: sympy oxuyursa cavab ondan (`source="sympy"`, növ yoxdur),
   oxumursa `status="unknown"`. **«Yoxlanmadı» heç vaxt «düzgündür» deyilmir.** Model olmayan addım
   nömrəsi qaytarsa da `unknown`-dur.

Yalnız modelin tapdığı səhv (`source="model"`) **təklifdir**: v3 golden-də yalançı həyəcan 0.41-dir
(hədəf < 0.20). UI bunu açıq yazır.

## Adapteri qoşmaq

Adapter repoda deyil (Google Drive-dadır). Server 1 nüvəlidir, torch QOYULMUR.

### A) vLLM (tövsiyə: Colab GPU + tunel)

Qəbz oxuyucusu ilə eyni baza modeldir, bir server iki adapteri verə bilər:

```bash
vllm serve Qwen/Qwen2.5-1.5B-Instruct --dtype half --api-key "$KEY" \
  --enable-lora --max-lora-rank 16 \
  --lora-modules sehv=/content/drive/MyDrive/sehv-detektivi/sehv-lora-v3 receipts=/content/drive/...
```

Hazır notebook: **`ml/vllm_sehv.ipynb`** (Colab T4, Run all) - Drive-dan v3-ü (və qəbz adapteri
varsa onu da) qaldırır, golden dəsti masterai yolu ilə ölçür, tunel açır və bu sətirləri çap edir:

```
VLLM_BASE_URL=https://<tunel>.trycloudflare.com
VLLM_API_KEY=<KEY>
SEHV_VLLM_MODEL=sehv
```

Ayrı vLLM serveri lazımdırsa `SEHV_VLLM_URL` / `SEHV_VLLM_API_KEY`. Yalnız `VLLM_BASE_URL`
Səhv Detektivini AÇMIR: adapterin adı (`SEHV_VLLM_MODEL`) olmalıdır.

### B) Lokal (GPU-lu kompüter, Colab)

```
pip install torch transformers peft bitsandbytes accelerate
SEHV_ADAPTER_PATH=/content/drive/MyDrive/sehv-detektivi/sehv-lora-v3   # və ya HF repo: istifadeci/sehv-lora-v3
```

Model ilk sorğuda yüklənir. Qovluq yoxdursa və ya torch/peft quraşdırılmayıbsa backend qurulmur,
servis sympy ilə işləməyə davam edir (`GET /me/diagnose` səbəbini `backend` sahəsində yazır).

## Ölçmə (`python -m evals.sehv`)

Golden dəst (`evals/datasets/sehv_golden.jsonl`, 100 nümunə) `diagnose` ilə üç rejimdə: yalnız sympy,
yalnız model, model+sympy. Səhv Detektivi reposunun `evaluate.py`-sindən fərqli olaraq tələbənin gördüyü
nəticəni ölçür: «yoxlanmadı» cavabı səhv sayılır, yalançı həyəcan və buraxılan səhv ayrıdır.
Modelsiz (CI): riyaziyyatda addım 87%, yalançı həyəcan 0%, məntiq 100% «yoxlanmadı».

## Kalibrasiya (hələ gözlənilir)

`notebooks/05_kalibrasiya.ipynb` (Səhv Detektivi reposu) val dəstində eşik seçir. Nəticə gələndə:

```
SEHV_NULL_THRESHOLD=0.xx
```

Eşik yalnız `null_prob` verən backend-də işləyir: **lokal** backend onu `scripts/calibrate.py` ilə
EYNİ üsulla hesablayır. vLLM chat API-si namizəd ehtimallarını vermir, orada eşik tətbiq olunmur
(cavabda `p_null` yoxdur), yalnız sympy veto işləyir. Yeni yoxlama qatı (məs. məntiq yoxlayıcısı)
`detector.Calibration`-a əlavə olunur.

## Sınanmayan

Bu repoda GPU yoxdur: real adapter nə vLLM, nə lokal backend ilə burada işlədilməyib. vLLM sorğusunun
forması saxta serverlə (`httpx.MockTransport`), lokal backend yalnız konfiqurasiya səviyyəsində sınanıb.
`ml/vllm_sehv.ipynb` də burada işlədilməyib (test yalnız JSON-u və xanaların sintaksisini yoxlayır).
