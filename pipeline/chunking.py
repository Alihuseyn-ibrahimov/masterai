from langchain_text_splitters import RecursiveCharacterTextSplitter

# ~1500 token hədəfi xarakter əsaslı yanaşdırılır (tiktoken kimi dəqiq token
# sayğacı əlavə asılılıq/şəbəkə riski yaradır) — orta hesabla ~4 xarakter/token
# qəbul edilir, ona görə 1500 token ≈ 6000 xarakter.
CHUNK_SIZE_CHARS = 6000
CHUNK_OVERLAP_CHARS = 600


def split(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE_CHARS,
        chunk_overlap=CHUNK_OVERLAP_CHARS,
    )
    return splitter.split_text(text)
