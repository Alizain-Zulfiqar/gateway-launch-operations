"""tests/test_file_attachments.py — file_attachments utility tests."""
from __future__ import annotations

import pytest
from pathlib import Path


def test_validate_accepted_extension(tmp_path):
    from core.file_attachments import validate_document_extension
    f = tmp_path / "report.pdf"
    f.write_text("fake pdf")
    assert validate_document_extension(str(f)) == ".pdf"


def test_validate_accepted_extension_case_insensitive(tmp_path):
    from core.file_attachments import validate_document_extension
    f = tmp_path / "photo.PNG"
    f.write_bytes(b"\x89PNG")
    assert validate_document_extension(str(f)) == ".png"


def test_validate_rejected_extension(tmp_path):
    from core.file_attachments import validate_document_extension
    f = tmp_path / "script.sh"
    f.write_text("#!/bin/bash")
    with pytest.raises(ValueError, match="Unsupported"):
        validate_document_extension(str(f))


def test_copy_attachment_creates_file(tmp_path):
    from core.file_attachments import copy_attachment
    src = tmp_path / "approval.pdf"
    src.write_bytes(b"%PDF-1.4 fake content")

    result = copy_attachment(str(src), subfolder="project_1", prefix="site_5_approved")

    assert "stored_path" in result
    assert "original_name" in result
    assert "extension" in result
    assert result["extension"] == ".pdf"
    assert result["original_name"] == "approval.pdf"
    assert Path(result["stored_path"]).exists()
    assert Path(result["stored_path"]).read_bytes() == b"%PDF-1.4 fake content"


def test_copy_attachment_subfolder_created(tmp_path, monkeypatch):
    from core import file_attachments
    import config

    new_docs_dir = tmp_path / "docs"
    monkeypatch.setattr(config, "DOCS_DIR", new_docs_dir)
    monkeypatch.setattr(file_attachments, "DOCS_DIR", new_docs_dir)

    src = tmp_path / "note.txt"
    src.write_text("some note")

    result = file_attachments.copy_attachment(str(src), subfolder="project_99", prefix="site_3_candidate")

    dest = Path(result["stored_path"])
    assert dest.exists()
    assert dest.parent == new_docs_dir / "project_99"


def test_copy_attachment_unique_names(tmp_path, monkeypatch):
    """Two copies of the same file get distinct stored names (timestamp)."""
    import time
    from core import file_attachments
    import config

    new_docs_dir = tmp_path / "docs"
    monkeypatch.setattr(config, "DOCS_DIR", new_docs_dir)
    monkeypatch.setattr(file_attachments, "DOCS_DIR", new_docs_dir)

    src = tmp_path / "doc.pdf"
    src.write_bytes(b"%PDF fake")

    r1 = file_attachments.copy_attachment(str(src), "sub", "prefix")
    time.sleep(1.1)  # ensure different timestamp second
    r2 = file_attachments.copy_attachment(str(src), "sub", "prefix")

    assert r1["stored_path"] != r2["stored_path"]
