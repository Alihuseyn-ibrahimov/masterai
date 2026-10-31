"""MasterAI-nin AI hissələri üçün qiymətləndirmə dəsti (MasterAI Classroom, gün 13).

İki rejim:
- **offline** (defolt, CI-da işləyir): LLM çağırılmır. Tutorun niyyət təyini,
  davam sualının birləşdirilməsi, BM25 axtarışı və qaydalı sual filtri ölçülür.
- **live** (`--live`): real modellər. Tutorun cavabları və AI yoxlama komandası
  etiketlənmiş hallarla müqayisə olunur, istəsən LLM hakim (`--judge`) cavabın
  mənbəyə sadiqliyini 1-5 qiymətləndirir.

İşlətmək: `python -m evals.run` (bax `evals/README.md`).
"""
