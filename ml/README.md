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
