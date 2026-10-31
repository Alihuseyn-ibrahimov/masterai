# Sual çətinliyi modeli (gün 15, PyTorch)

AI hər suala «asan / orta / çətin» yazır, amma bu onun **təxminidir**. Əsl
çətinlik tələbələrin cavablarındadır. Bu model sualın mətnindən tələbələrin onu
**neçə faiz düzgün cavablayacağını** proqnozlaşdırır və müəllim `suallar.html`-də
hər kartın altında görür: «Model: ~41% düzgün cavab gözlənilir → Çətin (AI «Asan» demişdi)».

```
sual mətni → 14 əlamət (pipeline/difficulty_features.py)
           → MLP 14 → 16 (ReLU) → 1 (sigmoid)   [PyTorch ilə öyrədilir]
           → JSON çəkilər → serverdə saf Python inferens (torch YOX)
```

## Addımlar

1. **Serverdə data çıxar** (tələbə məlumatı yoxdur, yalnız sual əlamətləri + faiz):
   ```bash
   cd /opt/masterai
   .venv/bin/python deploy/export_difficulty_data.py --data-dir data --out /root/cetinlik.csv
   ```
2. **Noutbukda və ya Colab-da öyrət:**
   ```bash
   pip install -r requirements-ml.txt
   python -m ml.train_difficulty --csv cetinlik.csv --out difficulty_model.json
   ```
   Skript modeli iki bazaya qarşı yoxlayır: «hamısına orta faiz» (MAE) və «AI-nın
   öz səviyyəsi» (səviyyə düzgünlüyü). Keçmirsə, açıq deyir: serverə qoyma.
3. **Serverə qoy:** `scp difficulty_model.json root@server:/opt/masterai/data/`.
   Restart lazım deyil, fayl dəyişəndə yenidən oxunur (`DIFFICULTY_MODEL_PATH` ilə yer dəyişir).

Real data hələ azdırsa zənciri sintetik dəstlə sına:
`python -m ml.train_difficulty --synthetic 600 --out /tmp/demo.json`.
Belə model `synthetic: true` ilə yazılır və server onu **heç vaxt göstərmir**.

## Niyə belə

- **Əlamətlər izah oluna biləndir** (uzunluq, rəqəmli variant, «deyil» inkarı, sual ilə
  cavabın ortaq sözləri, AI-nın səviyyəsi): embedding modeli 1 nüvəli serverə ağırdır,
  müəllim isə «niyə çətin?» sualına cavab görməlidir.
- **Çəki = cavab sayı:** 40 cavablı sualın faizi 5 cavablıdan etibarlıdır (çəkili BCE).
- **Erkən dayanma:** validasiya itkisi 30 epoxa yaxşılaşmırsa dayanır, ən yaxşı çəkilər qalır.

---

# QLoRA fine-tune: öz sual generatorumuz (gün 16)

Kiçik açıq modeli (Qwen2.5-3B-Instruct) MasterAI-nin **öz yaxşı sualları** üzərində
QLoRA ilə öyrədirik: baza model 4-bit NF4 yüklənib dondurulur, yalnız LoRA adapterləri
(r=16, ~0.5% parametr) öyrədilir. Pulsuz Colab T4 bəs edir.

1. **Dataset (serverdə):**
   ```bash
   cd /opt/masterai && .venv/bin/python -m ml.sft_dataset --data-dir data --out /root/sft
   ```
   Hazır banklardan «material parçası → suallar» cütləri. İstifadəçi mesajı produksiya
   promptu ilə bayt-bayt eynidir (`generation.user_prompt`, test qoruyur). Yalnız yaxşı
   suallar: qaydalı filtri keçən və AI yoxlama komandasının «fix» demədiyi. Train/val
   BANK üzrə bölünür (eyni material iki tərəfə düşmür).
2. **Colab:** `ml/qlora_mcq.ipynb`-i aç (GitHub → Colab), T4 seç, `train.jsonl` + `val.jsonl` yüklə,
   hamısını işlət. Paket versiyaları sabitlənib.
3. **Müqayisə:** notebook baza modeli və fine-tune-u eyni val dəstində sual yazdırır,
   `ml/score_generation.py` cədvəl çıxarır: JSON oxunurmu, say düzgündürmü, qaydalı filtr,
   uzunluqla özünü verən cavab, cavabın materiala bağlılığı.
4. **Saxla:** notebook adapteri baza ilə birləşdirib `masterai-mcq-merged/` yazır (gün 17: vLLM).

---

# vLLM ilə serving + sürət (gün 17)

`ml/vllm_serve.ipynb` (Colab T4): gün 16-nın birləşdirilmiş modelini `vllm serve` ilə
OpenAI-uyğun API kimi açır, `ml/bench_llm.py` ilə 1/4/8 paralel sorğuda TTFT, p50/p95
gecikmə və saniyədə token ölçür, HF `generate` ilə müqayisə edir və Cloudflare tuneli ilə
MasterAI serverinə qoşmaq üçün `.env` sətirlərini çap edir:

```
VLLM_BASE_URL=https://<tunel>.trycloudflare.com
VLLM_API_KEY=...
LLM_ORDER=vllm,groq,claude
```

Server `pipeline/providers.py`-də `vllm` provayderini qurur (sadə httpx, SDK yox). Colab
bağlananda tunel ölür və fallback zənciri sükutla Groq-a keçir; cavab `max_tokens`-də
kəsilsə də (yarımçıq JSON) növbəti provayder götürür.

```bash
python -m ml.bench_llm --concurrency 1,4,8 --requests 16   # VLLM_* .env-dən
python -m ml.bench_llm --groq --concurrency 1,4            # Groq ilə müqayisə
```
