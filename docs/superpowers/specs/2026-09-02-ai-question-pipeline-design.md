# MasterAI — AI Sual Generasiya Pipeline-ı (Dizayn Sənədi)

**Tarix:** 2026-09-02
**Status:** Təsdiqlənib (istifadəçi tərəfindən), implementasiya planına keçilir
**Əhatə dairəsi:** Yalnız bu alt-sistem — material daxil edilməsindən MCQ sual
siyahısı çıxana qədər olan pipeline. Auth, çat, Flutter UI, DB sxemi, n8n
workflow-un öz daxili qurulması bu sənədin əhatəsindən **kənardadır** — ayrı
spec-lər olaraq gələcəkdə dizayn ediləcək.

## 1. Problem və məqsəd

MasterAI dövlət qulluğu/magistratura imtahanlarına hazırlaşan tələbələr üçün
dərs materialından avtomatik MCQ (çoxseçimli) test sualları çıxarır. Bu
sənəd yalnız o "material → sual" çevrilməsini həyata keçirən mühərriki
təsvir edir: `masterai/pipeline/` Python paketi.

Paket FastAPI/DB/n8n-dən **asılı olmadan** işləməlidir — CLI-dan çağırılıb
nəticənin keyfiyyəti tez sınana bilsin (repo-nun "koda güvənmə, mənbədən
yoxla" prinsipi: burada mənbə real material üzərində çıxan real suallardır).

## 2. Giriş formatları

Üç material növü dəstəklənir, hər biri üçün ayrı ingestion modulu:

| Növ | Modul | Alət |
|---|---|---|
| Sayt linki | `ingestion/web_extractor.py` | BeautifulSoup (statik), Selenium (JS render lazımdırsa) |
| PDF (mətn təbəqəli) | `ingestion/pdf_extractor.py` | pypdf |
| Şəkil / skan olunmuş material | `ingestion/image_extractor.py` | pytesseract (AZ dil paketi ilə) |

Hər extractor eyni interfeysi həyata keçirir:

```python
def extract(source: MaterialSource) -> RawMaterial:
    """RawMaterial(text: str, metadata: dict) qaytarır ya da IngestionError atır."""
```

Extractor seçimi `MaterialSource.kind` sahəsinə görə edilir (`"link" |
"pdf" | "image"`), `pipeline.py`-dəki bir `if/elif` ilə — ayrı "factory"
abstraksiyasına ehtiyac yoxdur (3 sabit növ, dəyişməsi gözlənilmir).

## 3. Arxitektura

```
masterai/pipeline/
  ingestion/
    web_extractor.py
    pdf_extractor.py
    image_extractor.py
  chunking.py       # LangChain text splitter (~1500 token, overlap)
  providers.py       # Groq -> Claude -> Ollama(Qwen) fallback zənciri
  generation.py        # LCEL: chunk_prompt | llm | PydanticOutputParser
  dedup.py               # yaxın-dublikat sualları süzür
  models.py                # MCQQuestion, MaterialSource, PipelineResult
  pipeline.py                # generate_quiz(source, questions_per_chunk=3) -> PipelineResult
  cli.py                        # əl ilə sınaq üçün giriş nöqtəsi
tests/
  fixtures/            # nümunə PDF/HTML/şəkil test faylları
  test_ingestion.py
  test_chunking.py
  test_generation.py
```

**LLM provayder strategiyası (`providers.py`):** dildostu-nun
`chat_with_fallback` naxışı təkrarlanır — Groq əsas (sürətli, keyfiyyətli),
uğursuz olsa Claude, o da uğursuz olsa Ollama (lokal Qwen) ehtiyat. Fallback
zənciri hər çağırışda hansı provayderin işlədiyini loglayır (dildostu-dakı
`chat_ok provider=…` naxışı).

## 4. Data model (`models.py`)

```python
class MaterialSource(BaseModel):
    kind: Literal["link", "pdf", "image"]
    location: str          # URL və ya fayl yolu
    label: str | None = None   # istifadəçinin verdiyi ad (məs. "Konstitusiya hüququ - 3-cü fəsil")

class RawMaterial(BaseModel):
    text: str
    metadata: dict

class MCQQuestion(BaseModel):
    question: str
    options: list[str]         # tam 5 element
    correct_index: int         # 0-4
    explanation: str           # niyə düzgün cavab budur

class PipelineResult(BaseModel):
    questions: list[MCQQuestion]
    source: MaterialSource
    chunks_processed: int
    chunks_failed: int
```

`options` sahəsi validator ilə tam 5 element olmasını, `correct_index`-in
0-4 aralığında olmasını yoxlayır — parser bu şərtləri ödəməyən LLM çıxışını
avtomatik rədd edir (Pydantic validation error → retry məntiqinə düşür).

## 5. Data flow

```
MaterialSource
  → (kind-a görə) uyğun ingestion extractor
  → RawMaterial.text
  → chunking.split() → list[str] (~1500 token, overlap)
  → generation.generate_for_chunks(chunks, questions_per_chunk=3) — LCEL
      .batch() ilə paralel, hər chunk → prompt | llm (fallback zənciri) |
      PydanticOutputParser → o chunk üçün `questions_per_chunk` ədəd
      MCQQuestion
  → bütün chunk nəticələri birləşdirilir (ümumi sual sayı material
      uzunluğuna görə təbii şəkildə dəyişir — sabit ümumi say tələb
      olunmur)
  → dedup.filter() — sual mətnləri arasında `difflib.SequenceMatcher`
      oxşarlığı (məs. >0.85) olan cütlərdən biri atılır; MVP üçün embedding
      əsaslı oxşarlıq tələb olunmur
  → PipelineResult
```

## 6. Xəta idarəetməsi

- **Ingestion xətası** (sınıq PDF, ölü link, oxunmaz şəkil) → `IngestionError`
  atılır, yuxarı ötürülür. Səssizcə boş nəticə qaytarılmır.
- **Bütün LLM provayderləri uğursuz** → `PipelineError`. Yarımçıq/uydurma
  sual qaytarılmır — ya tam nəticə, ya açıq xəta.
- **Tək chunk-un parser xətası** (LLM səhv JSON qaytarır) → prompt-a
  "əvvəlki cavab sxemə uyğun deyildi" xatırlatması ilə **bir dəfə** retry.
  Yenə uğursuz olsa, o chunk atlanır (`chunks_failed` sayılır, warning
  loglanır), qalan chunk-lar davam edir — bir zəif chunk bütün materialı
  batırmasın.
- **Keyfiyyət həddi:** `len(questions) < 3` olarsa, `pipeline.py`
  `PipelineResult`-u uğursuz sayır (`PipelineError` atır) — kiçik/zəif quiz
  səssizcə istifadəçiyə göstərilmir.

## 7. Test strategiyası

- `test_ingestion.py`: hər extractor üçün `tests/fixtures/`-dəki real
  nümunə fayllarla (1 mətn-PDF, 1 statik HTML, 1 skan şəkil) — çıxan mətnin
  gözlənilən açar sözləri ehtiva etdiyini yoxlayır (tam mətn müqayisəsi yox,
  OCR/scraping determinist deyil).
- `test_chunking.py`: chunk ölçüsü, overlap düzgünlüyü, boş mətn kənar hal.
- `test_generation.py`: mock LLM cavabı ilə Pydantic validasiya (düzgün
  sxem qəbul olunur, yanlış sxem — məs. 4 variant — rədd olunub retry-a
  düşür).
- **Real sınaq (avtomatlaşdırılmamış, əl ilə):** CLI ilə real Groq API-yə
  qarşı, 20-30 real dövlət qulluğu/magistratura materialı üzərində —
  çıxan sualların keyfiyyətini istifadəçi əl ilə qiymətləndirir (repo-nun
  pilot metodologiyasındakı "keyfiyyətli 30 > keyfiyyətsiz 300" qaydası).
  Bu addım kod testi ilə əvəz oluna bilməz — nəticə mənbədən (real sualların
  məzmunundan) yoxlanılmalıdır.

## 8. Əhatə xaricində (gələcək spec-lər)

- FastAPI endpoint-i (`POST /pipeline/generate`) və n8n webhook orkestrasiyası
- Auth, DB sxemi (suallar haradan saxlanılacaq)
- Flutter UI, çat inteqrasiyası
- MCP server (admin "N sual yarat" alət çağırışı)
- Çətinlik səviyyəsi (asan/orta/çətin) — istifadəçi bu MVP-də istəmədi,
  gələcəkdə `MCQQuestion`-a `difficulty` sahəsi əlavə oluna bilər
