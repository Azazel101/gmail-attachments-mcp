"""Gmail API service + attachment operations (used by MCP tools and web UI)."""
from __future__ import annotations

import base64
import logging
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from . import config

LOG = logging.getLogger("gmail-mcp.service")


# ---------- Auth state ----------
def is_authenticated() -> bool:
    """Či máme platný (alebo refreshovateľný) token."""
    if not config.TOKEN_PATH.exists():
        return False
    try:
        creds = Credentials.from_authorized_user_file(
            str(config.TOKEN_PATH), config.SCOPES
        )
        if creds.valid:
            return True
        if creds.expired and creds.refresh_token:
            return True
        return False
    except Exception as exc:
        LOG.warning("Token check failed: %s", exc)
        return False


def get_user_email() -> str | None:
    """Vráti emailovú adresu prihláseného používateľa."""
    try:
        service = get_gmail_service()
        profile = service.users().getProfile(userId="me").execute()
        return profile.get("emailAddress")
    except Exception:
        return None


def get_gmail_service():
    """Vráti autentifikovaného Gmail API klienta."""
    if not config.TOKEN_PATH.exists():
        raise RuntimeError(
            "Not authenticated. Open web UI and click 'Sign in with Google'."
        )

    creds = Credentials.from_authorized_user_file(
        str(config.TOKEN_PATH), config.SCOPES
    )
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            config.TOKEN_PATH.write_text(creds.to_json())
            LOG.info("OAuth token refreshed")
        else:
            raise RuntimeError("Invalid credentials, please re-authenticate.")

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


# ---------- Helpers ----------
def safe_filename(name: str) -> str:
    keep = "-_.() "
    cleaned = "".join(c for c in name if c.isalnum() or c in keep).strip()
    return cleaned or "attachment"


def find_attachment_parts(payload: dict) -> list[dict]:
    """Rekurzívne nájdi všetky parts s prílohami."""
    found = []

    def walk(part: dict) -> None:
        if part.get("filename") and part.get("body", {}).get("attachmentId"):
            found.append({
                "filename": part["filename"],
                "mime_type": part.get("mimeType", "application/octet-stream"),
                "size": part.get("body", {}).get("size", 0),
                "attachment_id": part["body"]["attachmentId"],
            })
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    return found


# ---------- Operations ----------
def list_attachments_op(
    query: str = "has:attachment newer_than:7d",
    max_results: int = 20,
) -> dict[str, Any]:
    service = get_gmail_service()
    max_results = max(1, min(50, max_results))

    LOG.info("list_attachments query=%r max=%d", query, max_results)

    resp = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()

    results = []
    for msg_meta in resp.get("messages", []):
        msg = service.users().messages().get(
            userId="me", id=msg_meta["id"], format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        attachments = find_attachment_parts(msg["payload"])
        if not attachments:
            continue

        results.append({
            "message_id": msg["id"],
            "thread_id": msg["threadId"],
            "subject": headers.get("Subject", "(no subject)"),
            "from": headers.get("From", ""),
            "date": headers.get("Date", ""),
            "snippet": msg.get("snippet", "")[:200],
            "attachments": attachments,
        })

    return {
        "query": query,
        "total_messages": len(results),
        "messages": results,
    }


def download_attachment_op(
    message_id: str,
    attachment_id: str,
    filename: str,
    subfolder: str | None = None,
) -> dict[str, Any]:
    service = get_gmail_service()

    LOG.info("download_attachment msg=%s file=%s", message_id, filename)

    att = service.users().messages().attachments().get(
        userId="me", messageId=message_id, id=attachment_id
    ).execute()
    data = base64.urlsafe_b64decode(att["data"])

    target_dir = config.DOWNLOAD_DIR
    if subfolder:
        target_dir = config.DOWNLOAD_DIR / safe_filename(subfolder)
        target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = safe_filename(filename)
    target = target_dir / safe_name
    if target.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = target_dir / f"{target.stem}_{ts}{target.suffix}"

    target.write_bytes(data)

    return {
        "saved_to": str(target),
        "size_bytes": len(data),
        "filename": target.name,
        "subfolder": subfolder,
    }


def extract_attachment_op(
    message_id: str,
    attachment_id: str,
    filename: str,
    use_ocr_pipeline: bool = False,
) -> dict[str, Any]:
    service = get_gmail_service()

    LOG.info(
        "extract_attachment msg=%s file=%s ocr=%s",
        message_id, filename, use_ocr_pipeline,
    )

    att = service.users().messages().attachments().get(
        userId="me", messageId=message_id, id=attachment_id
    ).execute()
    data = base64.urlsafe_b64decode(att["data"])

    ext = Path(filename).suffix.lower()

    # Forward na OCR pipeline ak je nakonfigurovaný
    if use_ocr_pipeline and config.OCR_PIPELINE_URL:
        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(
                    config.OCR_PIPELINE_URL,
                    files={"file": (filename, data)},
                )
                resp.raise_for_status()
                return {
                    "extraction_method": "ocr_pipeline",
                    "filename": filename,
                    "result": resp.json(),
                }
        except Exception as exc:
            LOG.warning("OCR pipeline failed, falling back to local: %s", exc)

    # Local extraction
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(data))
            pages = [p.extract_text() or "" for p in reader.pages]
            text = "\n\n".join(pages)
            return {
                "extraction_method": "pypdf",
                "filename": filename,
                "page_count": len(pages),
                "text": text,
                "char_count": len(text),
            }
        except Exception as exc:
            return {"error": f"PDF extraction failed: {exc}", "filename": filename}

    elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp"):
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(BytesIO(data))
            text = pytesseract.image_to_string(img, lang="slk+eng")
            return {
                "extraction_method": "tesseract",
                "filename": filename,
                "image_size": list(img.size),
                "text": text,
                "char_count": len(text),
            }
        except Exception as exc:
            return {"error": f"OCR failed: {exc}", "filename": filename}

    elif ext in (".txt", ".csv", ".log", ".md", ".json", ".xml", ".html"):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1", errors="replace")
        return {
            "extraction_method": "plain_text",
            "filename": filename,
            "text": text,
            "char_count": len(text),
        }

    return {
        "error": f"Unsupported file type: {ext}",
        "filename": filename,
        "size_bytes": len(data),
    }
