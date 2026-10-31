"""AI tutoru NeMo Guardrails ilə bükür (MasterAI Classroom, gün 20).

    pip install -r requirements-guardrails.txt
    python -m nemo_rails.rails "Milli Məclis neçə deputatdan ibarətdir?"

Server NeMo-nu İŞLƏTMİR: eyni qaydalar `pipeline/guardrails.py`-də saf Python-dur
və tutor qrafının içindədir (NeMo onnxruntime, fastembed kimi ağır paketlər və hər sorğuya asinxron
dövr əlavə edir, 1 nüvəli serverə lazım deyil). Bu modul eyni qaydaları NeMo-nun
rail modeli ilə göstərir: Colang axını (`config/rails.co`) → Python action →
`pipeline.guardrails`. Yəni qaydanı dəyişmək üçün bir yer var.

Axın: istifadəçi mesajı → input rail (`masterai_check_input`) → bloklanmayıbsa
əsas «LLM» = `TutorModel` (LangGraph tutoru: axtarış + LLM + öz çıxış yoxlaması)
→ output rail (`masterai_check_output`: təlimat sızması, şəxsi məlumat) → cavab.
"""

from __future__ import annotations

import sys
from pathlib import Path

from nemoguardrails import LLMRails, RailsConfig
from nemoguardrails.actions import action
from nemoguardrails.types import LLMResponse

from pipeline import guardrails
from pipeline.rag import TUTOR_SYSTEM_PROMPT, Document
from pipeline.tutor_graph import QUIZ_SYSTEM_PROMPT, run_tutor

CONFIG_DIR = Path(__file__).parent / "config"
NOT_FOUND_TEXT = "Bu barədə dərs materiallarında məlumat tapmadım."
SECRETS = [TUTOR_SYSTEM_PROMPT, QUIZ_SYSTEM_PROMPT]


def _last_user_text(prompt) -> str:
    if isinstance(prompt, str):
        return prompt
    for message in reversed(prompt):
        role = getattr(message, "role", None)
        if getattr(role, "value", role) == "user":
            return message.content or ""
    return ""


def reply_text(state: dict) -> str:
    kind = state.get("kind")
    if kind == "quiz" and state.get("quiz"):
        quiz = state["quiz"]
        options = "\n".join(f"{chr(65 + i)}) {o}" for i, o in enumerate(quiz.options))
        return f"{quiz.question}\n{options}"
    if kind in ("answer", "offtopic", "blocked"):
        return state.get("answer", "")
    return NOT_FOUND_TEXT


class TutorModel:
    """NeMo-nun `LLMModel` protokolu: «generate» = bizim tutor qrafı."""

    model_name = "masterai-tutor"
    provider_name = "masterai"
    provider_url = None

    def __init__(self, documents: list[Document], tutor=run_tutor, **tutor_kwargs):
        self.documents = documents
        self.tutor = tutor
        self.tutor_kwargs = tutor_kwargs
        self.last_state: dict | None = None

    async def generate_async(self, prompt, *, stop=None, **kwargs) -> LLMResponse:
        self.last_state = self.tutor(_last_user_text(prompt), self.documents, [], **self.tutor_kwargs)
        return LLMResponse(content=reply_text(self.last_state))

    async def stream_async(self, prompt, *, stop=None, **kwargs):
        response = await self.generate_async(prompt, stop=stop, **kwargs)
        yield response.content  # pragma: no cover - axın istifadə olunmur


@action(name="masterai_check_input")
async def check_input_action(context: dict | None = None) -> bool:
    return guardrails.check_input((context or {}).get("user_message") or "").blocked


@action(name="masterai_check_output")
async def check_output_action(context: dict | None = None) -> bool:
    text = (context or {}).get("bot_message") or ""
    return guardrails.leaks(text, SECRETS) or bool(guardrails.mask_pii(text)[1])


def build_rails(documents: list[Document], **tutor_kwargs) -> tuple[LLMRails, TutorModel]:
    model = TutorModel(documents, **tutor_kwargs)
    rails = LLMRails(RailsConfig.from_path(str(CONFIG_DIR)), llm=model)
    rails.register_action(check_input_action, "masterai_check_input")
    rails.register_action(check_output_action, "masterai_check_output")
    return rails, model


def ask(rails: LLMRails, question: str) -> str:
    return rails.generate(messages=[{"role": "user", "content": question}])["content"]


def main(argv: list[str] | None = None) -> int:
    from evals.run import load_documents

    args = sys.argv[1:] if argv is None else argv
    if not args:
        print('İstifadə: python -m nemo_rails.rails "sual"')
        return 2
    rails, _ = build_rails(load_documents())
    print(ask(rails, " ".join(args)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
