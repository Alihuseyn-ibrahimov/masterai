from typing import Literal

from pydantic import BaseModel, Field


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
