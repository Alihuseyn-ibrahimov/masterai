import pytest
from pydantic import ValidationError

from pipeline.models import MaterialSource, MCQQuestion, PipelineResult, RawMaterial


def _valid_options():
    return ["Bakı", "Gəncə", "Sumqayıt", "Şəki", "Naxçıvan"]


class TestMaterialSource:
    def test_accepts_valid_kinds(self):
        for kind in ("link", "pdf", "image"):
            source = MaterialSource(kind=kind, location="x")
            assert source.kind == kind

    def test_rejects_unknown_kind(self):
        with pytest.raises(ValidationError):
            MaterialSource(kind="video", location="x")

    def test_label_is_optional(self):
        source = MaterialSource(kind="pdf", location="materials/dq.pdf")
        assert source.label is None


class TestRawMaterial:
    def test_holds_text_and_metadata(self):
        raw = RawMaterial(text="mətn", metadata={"pages": 3})
        assert raw.text == "mətn"
        assert raw.metadata == {"pages": 3}


class TestMCQQuestion:
    def test_accepts_exactly_five_options(self):
        q = MCQQuestion(
            question="Azərbaycanın paytaxtı hansıdır?",
            options=_valid_options(),
            correct_index=0,
            explanation="Bakı Azərbaycanın paytaxtıdır.",
        )
        assert len(q.options) == 5

    def test_rejects_four_options(self):
        with pytest.raises(ValidationError):
            MCQQuestion(
                question="...",
                options=_valid_options()[:4],
                correct_index=0,
                explanation="...",
            )

    def test_rejects_six_options(self):
        with pytest.raises(ValidationError):
            MCQQuestion(
                question="...",
                options=_valid_options() + ["Şuşa"],
                correct_index=0,
                explanation="...",
            )

    @pytest.mark.parametrize("bad_index", [-1, 5, 100])
    def test_rejects_out_of_range_correct_index(self, bad_index):
        with pytest.raises(ValidationError):
            MCQQuestion(
                question="...",
                options=_valid_options(),
                correct_index=bad_index,
                explanation="...",
            )

    @pytest.mark.parametrize("good_index", [0, 1, 2, 3, 4])
    def test_accepts_every_in_range_correct_index(self, good_index):
        q = MCQQuestion(
            question="...",
            options=_valid_options(),
            correct_index=good_index,
            explanation="...",
        )
        assert q.correct_index == good_index


class TestPipelineResult:
    def test_holds_questions_and_source(self):
        source = MaterialSource(kind="link", location="https://example.az/derslik")
        question = MCQQuestion(
            question="...",
            options=_valid_options(),
            correct_index=1,
            explanation="...",
        )
        result = PipelineResult(
            questions=[question],
            source=source,
            chunks_processed=1,
            chunks_failed=0,
        )
        assert result.questions == [question]
        assert result.chunks_processed == 1
        assert result.chunks_failed == 0
