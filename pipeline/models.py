from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Sualın çətinlik səviyyəsi (2026-10-30, Faza 2). Müəllim yükləmədə
# faiz bölgüsü seçir, AI hər suala səviyyə yazır.
DIFFICULTY_LEVELS = ("asan", "orta", "çətin")
Difficulty = Literal["asan", "orta", "çətin"]

# Model bəzən ingiliscə, böyük hərflə və ya "ə"-siz yazır — bunlar
# sualı RƏDD etmək üçün səbəb deyil, düzgün dəyərə çevrilir.
_DIFFICULTY_ALIASES = {
    "asan": "asan", "easy": "asan",
    "orta": "orta", "medium": "orta", "moderate": "orta",
    "çətin": "çətin", "cetin": "çətin", "çetin": "çətin", "hard": "çətin", "difficult": "çətin",
}


def normalize_difficulty(value) -> str | None:
    """Tanınmayan dəyər `None` olur (səviyyəsiz sual), xəta yox."""
    if not isinstance(value, str):
        return None
    return _DIFFICULTY_ALIASES.get(value.strip().lower())


class MaterialSource(BaseModel):
    kind: Literal["link", "pdf", "image"]
    location: str
    label: str | None = None


class RawMaterial(BaseModel):
    text: str
    metadata: dict = Field(default_factory=dict)


class MCQQuestion(BaseModel):
    question: str
    options: list[str] = Field(min_length=5, max_length=5)
    correct_index: int = Field(ge=0, le=4)
    explanation: str
    # Köhnə suallarda və səviyyə yazmayan cavablarda `None`.
    difficulty: Difficulty | None = None

    @field_validator("difficulty", mode="before")
    @classmethod
    def _normalize_difficulty(cls, value):
        return normalize_difficulty(value)


class PipelineResult(BaseModel):
    questions: list[MCQQuestion]
    source: MaterialSource
    chunks_processed: int
    chunks_failed: int
    # Çağıranın istədiyi ümumi sual sayı (bax `pipeline.generate_quiz`,
    # `target_question_count`) — `len(questions)` bundan az ola bilər
    # (material qısadırsa), çağıran (server) bu fərqi istifadəçiyə
    # bildirmək üçün istifadə edir.
    requested_question_count: int
    # Reading bankı (spec 2026-09-29 §5): tələbəyə sualların üstündə
    # göstəriləcək mətn. Digər banklarda None.
    passage: str | None = None
