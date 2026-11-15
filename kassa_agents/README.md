# Kassa agentləri (Kurs Kassası, addım 6)

Kurs rəhbəri üçün iki agent komandası. **Rəhbərin kompüterində** işləyir: CrewAI və
AutoGen serverə qoyulmur. Data mövcud `GET /live/kassa` ilə rəhbərin öz hesabı ilə
gəlir, agentlər heç nə yazmır.

## Quraşdırma

```bash
export MASTERAI_API=https://masterai.prdostu.com
export MASTERAI_EMAIL=... MASTERAI_PASSWORD=...     # və ya MASTERAI_TOKEN
export GROQ_API_KEY=...                              # və ya LLM_ORDER/VLLM_BASE_URL

# Aylıq hesabat (CrewAI)
python -m venv .venv-crew && .venv-crew/bin/pip install -r requirements.txt -r requirements-agents.txt
.venv-crew/bin/python -m kassa_agents.cli report --month 2026-11 --out kassa-2026-11.md

# Kassaya sual (AutoGen, AYRI venv: protobuf toqquşması)
python -m venv .venv-autogen && .venv-autogen/bin/pip install -r requirements.txt -r requirements-autogen.txt
.venv-autogen/bin/python -m kassa_agents.cli ask "Hansı qrupda borc ən çoxdur?" --show-sql
```

## Necə qorunur

- **Ad LLM-ə getmir.** Borclular «Şagird 1», «Şagird 2» olur, sualdakı «Kamran» da
  ləqəbə çevrilir. Real ad cavaba yalnız sizin kompüterinizdə qaytarılır.
- **Rəqəm uydurulmur.** Kassada (və ya SQL nəticəsində) olmayan rəqəm daşıyan cümlə
  atılır. Hesabatın altında neçə cümlənin atıldığı yazılır.
- **SQL yalnız oxuyur.** Sorğu real bazaya yox, Kassa xülasəsinin yaddaşdakı anonim
  surətinə gedir: bir SELECT, yazma/ATTACH/PRAGMA rədd, addım və sətir limiti.
- **Prompt injection** (`pipeline/guardrails.py`, AI tutor ilə eyni qaydalar) LLM-ə
  çatmadan bloklanır.

Testlər: `tests/test_kassa_agents.py` (qoruyucu qat CI-da; CrewAI/AutoGen testləri öz
venv-lərində işləyir, CI-da keçilir).
