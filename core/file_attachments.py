"""
core/file_attachments.py — Document attachment utilities for project documents.
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from config import ACCEPTED_DOCUMENT_EXTENSIONS, DOCS_DIR


def validate_document_extension(file_path: str) -> str:
    """
    Validate that file_path has an accepted extension.
    Returns the extension (lowercase, with leading dot).
    Raises ValueError for unsupported extensions.
    """
    ext = Path(file_path).suffix.lower()
    if ext not in ACCEPTED_DOCUMENT_EXTENSIONS:
        accepted = ", ".join(sorted(ACCEPTED_DOCUMENT_EXTENSIONS))
        raise ValueError(
            f"Unsupported file type '{ext}'. Accepted types: {accepted}"
        )
    return ext


def copy_attachment(source_path: str, subfolder: str, prefix: str) -> dict:
    """
    Copy a document into the project documents directory.

    Returns dict with keys:
      stored_path   — absolute path of the copied file (str)
      original_name — original filename (str)
      extension     — lowercase extension with dot (str)
    """
    ext = validate_document_extension(source_path)
    dest_dir = DOCS_DIR / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    original_name = Path(source_path).name
    stored_name = f"{prefix}_{timestamp}{ext}"
    dest_path = dest_dir / stored_name

    shutil.copy2(source_path, dest_path)

    return {
        "stored_path": str(dest_path),
        "original_name": original_name,
        "extension": ext,
    }


def open_attachment(stored_path: str) -> None:
    """Open a stored attachment with the OS default application."""
    from core.utils import open_local_path
    open_local_path(stored_path)


# ── External document links (Pre-28B-1) ───────────────────────────────────────
# For contract documents the authoritative source stays outside the application;
# we store links only and never copy the file.

class DocumentNotReachableError(Exception):
    """Raised when neither the URL nor the UNC path for an external document
    can be opened."""
    pass


def store_external_link(url, unc_path, label: str = "") -> dict:
    """
    Store metadata about an external document link. Does NOT copy the file.
    Requires at least one of url or unc_path. Returns a dict suitable for the
    platform_contracts document_url / document_unc_path columns.
    """
    if not url and not unc_path:
        raise ValueError("At least one of url or unc_path must be provided.")
    return {
        "document_url": url or None,
        "document_unc_path": unc_path or None,
        "label": label,
    }


def open_external_document(url, unc_path) -> None:
    """
    Open an external document in the default OS application. Tries the URL first
    (webbrowser), then falls back to the UNC path (os.startfile on Windows).
    Raises DocumentNotReachableError with per-attempt reasons if both fail.
    """
    import webbrowser
    errors = []

    if url:
        try:
            webbrowser.open(url)
            return
        except Exception as e:
            errors.append(f"URL failed: {e}")

    if unc_path:
        try:
            from core.utils import open_local_path
            open_local_path(unc_path)
            return
        except Exception as e:
            errors.append(f"UNC path failed: {e}")

    raise DocumentNotReachableError(
        "Could not open document. " + " | ".join(errors)
        + " Verify the URL is accessible in your browser and the UNC path is "
        "reachable on your network."
    )
