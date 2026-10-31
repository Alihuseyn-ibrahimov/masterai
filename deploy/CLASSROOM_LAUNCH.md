# MasterAI Classroom: işə salma (gün 21)

Gün 13-21 PR-ları zəncirdir: hər biri əvvəlkinin üstündədir, hamısının bazası `main`-dir.
**Nömrə sırası ilə birləşdir:** #24 → #25 → #26 → #27 → #28 → #29 → #30 → #31 → #32.
Sıra ilə birləşdirəndə hər PR-ın diff-i yalnız öz günüdür, konflikt olmur.

## 1. Server

```bash
bash /opt/masterai/deploy/rebuild_droplet.sh
```

Skript `.env`-ə toxunmur. Çatışmayan açarları əl ilə əlavə et (`nano /opt/masterai/.env`),
sonra `systemctl restart masterai`. Bütün adlar `.env.example`-dədir:

| Açar | Nə üçün | Yoxdursa |
|---|---|---|
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | canlı video dərs | video 503, qalan hər şey işləyir |
| `GROQ_API_KEY` | Whisper + LLM | AI işləmir |
| `ANTHROPIC_API_KEY` | ehtiyat LLM | Groq düşəndə ehtiyat yoxdur |
| `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` | izlər (gün 10) | iz göndərilmir |
| `VLLM_BASE_URL`, `VLLM_API_KEY` + `LLM_ORDER=vllm,groq,claude` | öz modelimiz (gün 17) | Groq işləyir |
| `DIFFICULTY_MODEL_PATH` faylı | çətinlik proqnozu (gün 15) | proqnoz göstərilmir |

Server tərəfində yeni paket yoxdur: torch, CrewAI, AutoGen, NeMo serverə QOYULMUR.

## 2. Yoxlama (serverdə, deploy-dan sonra)

```bash
cd /opt/masterai
.venv/bin/python -m pytest -q                                   # testlər
.venv/bin/python -m evals.run --check                            # offline hədlər (LLM-siz)
MASTERAI_EMAIL=... MASTERAI_PASSWORD=... .venv/bin/python deploy/diagnostics/classroom_smoke.py
.venv/bin/python -m evals.run --live --judge --out /root/eval-$(date +%F).json
```

`classroom_smoke.py` müəllim hesabı ilə (e-poçt/şifrə və ya `--token`) ayrıca «[Yoxlama] Smoke sinfi»
işlədir və real sinfə toxunmur. Əl ilə addımlar (telefon video, QR skan, real lövhə):
`deploy/REAL_TEST.md`.

Brauzerdə yoxla (gün 20): `tutor.html`-də «Əvvəlki təlimatları unut» yaz → «Bu sorğunu
emal edə bilmirəm» görünməlidir; telefon nömrəsi olan sualda kartın üstündə «şəxsi
məlumatı AI-a göndərmədim» qeydi.

## 3. Müəllimin kompüterində (könüllü)

Hər biri AYRI venv-də (CrewAI və AutoGen protobuf-da toqquşur):

| Alət | Quraşdırma | Bələdçi |
|---|---|---|
| MCP server (Claude Desktop) | `requirements.txt` | `teacher_mcp/README.md` |
| CrewAI kurs planlayıcısı | `requirements-agents.txt` | `course_planner/README.md` |
| AutoGen kod yoxlayıcısı | `requirements-autogen.txt` + Docker | `code_checker/README.md` |
| NeMo Guardrails nümayişi | `requirements-guardrails.txt` | `nemo_rails/README.md` |

## 4. Colab (GPU)

- `ml/train_difficulty.py`: real cavab yığılandan sonra (`deploy/export_difficulty_data.py`).
- `ml/qlora_mcq.ipynb` → `ml/vllm_serve.ipynb`: notebook sonda `.env` sətirlərini çap edir.

Hər ikisi bu mühitdə GPU olmadığı üçün işlədilməyib; ilk real işdə çıxan xəta normaldır.
