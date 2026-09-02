import io

import pytest
from fastapi import UploadFile

from server.uploads import PayloadTooLarge, save_upload


def _upload_file(content: bytes, filename: str) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content))


@pytest.mark.asyncio
async def test_save_upload_writes_file_and_returns_path(tmp_path):
    upload = _upload_file(b"salam dunya", filename="materialim.pdf")

    path = await save_upload(upload, upload_dir=str(tmp_path), max_bytes=1024)

    assert path.startswith(str(tmp_path))
    with open(path, "rb") as f:
        assert f.read() == b"salam dunya"


@pytest.mark.asyncio
async def test_save_upload_uses_uuid_name_not_original_filename(tmp_path):
    upload = _upload_file(b"data", filename="../../etc/passwd")

    path = await save_upload(upload, upload_dir=str(tmp_path), max_bytes=1024)

    assert "passwd" not in path
    assert ".." not in path


@pytest.mark.asyncio
async def test_save_upload_preserves_extension(tmp_path):
    upload = _upload_file(b"img-bytes", filename="şəkil.png")

    path = await save_upload(upload, upload_dir=str(tmp_path), max_bytes=1024)

    assert path.endswith(".png")


@pytest.mark.asyncio
async def test_save_upload_rejects_oversized_file(tmp_path):
    big_content = b"x" * 100
    upload = _upload_file(big_content, filename="big.pdf")

    with pytest.raises(PayloadTooLarge):
        await save_upload(upload, upload_dir=str(tmp_path), max_bytes=50)

    assert list(tmp_path.iterdir()) == []
