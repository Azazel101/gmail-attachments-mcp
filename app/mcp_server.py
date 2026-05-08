"""MCP server exposing Gmail tools via HTTP transport."""
from __future__ import annotations

import logging
from typing import Any

from fastmcp import FastMCP

from . import gmail_service

LOG = logging.getLogger("gmail-mcp.server")

mcp = FastMCP(
    name="gmail-attachments",
    instructions=(
        "Gmail attachment access. Use list_attachments to discover emails, "
        "download_attachment to save files, extract_attachment to get text content."
    ),
)


@mcp.tool
def list_attachments(
    query: str = "has:attachment newer_than:7d",
    max_results: int = 20,
) -> dict[str, Any]:
    """
    Find emails with attachments matching a Gmail search query.

    Args:
        query: Gmail search query (same syntax as Gmail search bar).
               Examples:
                 "has:attachment from:fakturacia@example.sk newer_than:30d"
                 "has:attachment subject:dodací list newer_than:7d"
        max_results: Max messages to return (1-50, default 20).

    Returns:
        List of messages with their attachment metadata.
    """
    return gmail_service.list_attachments_op(query=query, max_results=max_results)


@mcp.tool
def download_attachment(
    message_id: str,
    attachment_id: str,
    filename: str,
    subfolder: str | None = None,
) -> dict[str, Any]:
    """
    Download an attachment to local storage.

    Args:
        message_id: Message ID from list_attachments.
        attachment_id: Attachment ID from list_attachments.
        filename: Original filename.
        subfolder: Optional subfolder name (e.g. 'invoices', 'delivery-notes').
    """
    return gmail_service.download_attachment_op(
        message_id=message_id,
        attachment_id=attachment_id,
        filename=filename,
        subfolder=subfolder,
    )


@mcp.tool
def extract_attachment(
    message_id: str,
    attachment_id: str,
    filename: str,
    use_ocr_pipeline: bool = False,
) -> dict[str, Any]:
    """
    Download an attachment and extract its text content.

    PDFs are parsed with pypdf, images via tesseract OCR (slk+eng), or
    forwarded to a configured OCR pipeline service.

    Args:
        message_id: Message ID.
        attachment_id: Attachment ID.
        filename: Filename (extension determines extraction method).
        use_ocr_pipeline: If True and OCR_PIPELINE_URL is set, forward to that service.
    """
    return gmail_service.extract_attachment_op(
        message_id=message_id,
        attachment_id=attachment_id,
        filename=filename,
        use_ocr_pipeline=use_ocr_pipeline,
    )
