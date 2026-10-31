# Eval dəsti (MasterAI Classroom, gün 13)

AI hissələrinin keyfiyyəti rəqəmlə ölçülür: tutor (RAG + LangGraph agent) və
çox agentli sual yoxlaması. Prompt, model və ya axtarış dəyişəndə «yaxşılaşdı,
yoxsa pisləşdi?» sualına cavab budur.

## İşlətmək

```bash
python -m evals.run                    # offline, LLM-siz (CI da bunu yoxlayır)
python -m evals.run --live --judge --out eval.json   # real modellər
```

Serverdə (açarlar `/opt/masterai/.env`-dədir):

```bash
cd /opt/masterai && .venv/bin/python -m evals.run --live --judge --out /root/eval-$(date +%F).json
```

## Dəst (`datasets/`)

| Fayl | Nə var |
|---|---|
| `materials.json` | 7 mənbə: Konstitusiya, Milli Məclis, Prezident, 1918, fotosintez, Python, RAG |
| `tutor.jsonl` | 30 sual: gözlənilən nəticə (`answer`/`quiz`/`not_found`/`offtopic`), mənbə, açar sözlər; davam sualları `history` ilə |
| `review.jsonl` | 16 test sualı, etiketli: `ok` və ya `fix` + problem (`wrong_answer`, `giveaway`, `two_correct`, `self_answering`, `not_in_material`) |

## Metrikalar

**Offline** (hər PR-da, `tests/test_evals.py` hədləri qoruyur):
- niyyət düzgünlüyü, axtarış hit@1 / hit@4 / MRR (düzgün parça tapılmasa, ən yaxşı model də düzgün cavab verməz);
- qaydalı sual filtri (`quality.py`): precision/recall. Faktı yoxlaya bilmir - bu rəqəm AI komandası üçün **bazadır**.

**Live:**
- tutor: nəticə növü, düzgün mənbə, açar söz recall, `[n]` istinadlarının düzgünlüyü,
  **«tapmadım» deyə bilmə** (materialda olmayan sualda uydurmur), quiz forması, vaxt;
- `--judge`: ayrıca LLM hakim cavabın parçalara sadiqliyini 1-5 qiymətləndirir;
- AI yoxlama komandası: precision/recall/F1, problem növü üzrə recall, «yoxlanmadı» sayı.

## Qaydalar

- Hal əlavə edəndə açar söz gözlənilən mənbədə olmalıdır (test yoxlayır).
- Offline hədd düşərsə həddi aşağı salma: ya reqressiyadır, ya dəst səhvdir.
- Dəstin ilk işində iki real səhv tapıldı: «Təşəkkür edirəm» və «Çox sağ ol» tutorda
  izah sualı sayılırdı (LLM boş yerə çağırılırdı), bir etiketli sualın özündə isə düzgün
  variant ən uzun idi - qayda haqlı çıxdı, dəst düzəldildi.
