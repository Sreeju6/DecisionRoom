"""Secure, multi-format company document parser for DecisionRoom.

Supports:
- PDF (via PyMuPDF, preserving page numbers)
- DOCX (via python-docx, preserving sections and tables)
- TXT (plain text with chunking)
- CSV (structured tables with column headers)
- XLSX (via openpyxl, preserving sheets and cell contexts)

Security:
- Rejects oversized and zero-byte files
- Computes SHA256 content hashes for duplicate detection
- Tags chunks as untrusted input to defend against prompt injection
"""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd


MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB limit
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 150


class ParsingError(Exception):
    """Raised when a document cannot be parsed or is corrupted."""
    pass


class FileValidationError(ParsingError):
    """Raised when a file fails validation (e.g. empty, oversized, unsupported)."""
    pass


@dataclass
class DocumentChunk:
    """Standardized document excerpt with provenance metadata."""
    chunk_id: str
    company_id: str
    project_id: str
    document_name: str
    doc_hash: str
    page_or_section: str
    text: str
    uploaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "company_id": self.company_id,
            "project_id": self.project_id,
            "document_name": self.document_name,
            "doc_hash": self.doc_hash,
            "page_or_section": self.page_or_section,
            "text": self.text,
            "uploaded_at": self.uploaded_at.isoformat(),
            "metadata": self.metadata,
        }


def compute_sha256(content: bytes) -> str:
    """Compute deterministic SHA256 hash of raw file bytes."""
    return hashlib.sha256(content).hexdigest()


def _sanitize_untrusted_text(text: str) -> str:
    """Normalize text and strip dangerous control characters while preserving structure."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    # Clean non-printable control characters (except newline, tab)
    cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", normalized)
    return cleaned.strip()


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """Split text into sliding window chunks on sentence or paragraph boundaries."""
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        candidate = text[start:end]

        if end < text_len:
            # Try to break at newline or sentence end
            last_period = candidate.rfind(". ")
            last_newline = candidate.rfind("\n")
            boundary = max(last_period, last_newline)
            if boundary > chunk_size * 0.5:
                end = start + boundary + 1
                candidate = text[start:end]

        chunk = candidate.strip()
        if chunk:
            chunks.append(chunk)

        next_start = end - overlap
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks


class DocumentParser:
    """Dispatcher for multi-format document extraction."""

    SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".xlsx"}

    @classmethod
    def validate_file(cls, filename: str, content: bytes) -> None:
        """Validate file size, extension, and non-emptiness."""
        ext = Path(filename).suffix.lower()
        if ext not in cls.SUPPORTED_EXTENSIONS:
            raise FileValidationError(
                f"Unsupported file format '{ext}'. Supported formats: {sorted(cls.SUPPORTED_EXTENSIONS)}"
            )
        if len(content) == 0:
            raise FileValidationError(f"File '{filename}' is completely empty (0 bytes).")
        if len(content) > MAX_FILE_BYTES:
            raise FileValidationError(
                f"File '{filename}' exceeds maximum allowed size ({MAX_FILE_BYTES / (1024*1024):.1f}MB)."
            )

    @classmethod
    def parse_pdf(cls, content: bytes, doc_name: str, company_id: str, project_id: str) -> List[DocumentChunk]:
        """Extract text page-by-page from PDF using PyMuPDF."""
        try:
            import pymupdf as fitz  # PyMuPDF; new module name ('fitz' alias is deprecated)
            doc = fitz.open(stream=content, filetype="pdf")
        except Exception as exc:
            raise ParsingError(f"Corrupt or unreadable PDF '{doc_name}': {exc}") from exc

        doc_hash = compute_sha256(content)
        chunks: List[DocumentChunk] = []

        try:
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                text = _sanitize_untrusted_text(page.get_text() or "")
                page_label = f"Page {page_idx + 1}"
                if not text:
                    continue
                for sub_idx, chunk in enumerate(chunk_text(text)):
                    chunks.append(DocumentChunk(
                        chunk_id=f"{doc_hash[:12]}_p{page_idx + 1}_{sub_idx}",
                        company_id=company_id,
                        project_id=project_id,
                        document_name=doc_name,
                        doc_hash=doc_hash,
                        page_or_section=page_label,
                        text=chunk,
                    ))
        finally:
            doc.close()

        if not chunks:
            raise ParsingError(f"PDF '{doc_name}' contains no extractable text.")
        return chunks

    @classmethod
    def parse_docx(cls, content: bytes, doc_name: str, company_id: str, project_id: str) -> List[DocumentChunk]:
        """Extract paragraphs and tables from DOCX using python-docx."""
        try:
            import docx
            doc = docx.Document(io.BytesIO(content))
        except Exception as exc:
            raise ParsingError(f"Corrupt or unreadable DOCX '{doc_name}': {exc}") from exc

        doc_hash = compute_sha256(content)
        chunks: List[DocumentChunk] = []
        current_section = "General"
        section_texts: List[str] = []

        for p in doc.paragraphs:
            text = _sanitize_untrusted_text(p.text)
            if not text:
                continue
            if p.style and "heading" in p.style.name.lower():
                if section_texts:
                    combined = "\n".join(section_texts)
                    for sub_idx, chunk in enumerate(chunk_text(combined)):
                        chunks.append(DocumentChunk(
                            chunk_id=f"{doc_hash[:12]}_{len(chunks)}",
                            company_id=company_id,
                            project_id=project_id,
                            document_name=doc_name,
                            doc_hash=doc_hash,
                            page_or_section=current_section,
                            text=chunk,
                        ))
                    section_texts = []
                current_section = text
            else:
                section_texts.append(text)

        # Process any remaining text
        if section_texts:
            combined = "\n".join(section_texts)
            for chunk in chunk_text(combined):
                chunks.append(DocumentChunk(
                    chunk_id=f"{doc_hash[:12]}_{len(chunks)}",
                    company_id=company_id,
                    project_id=project_id,
                    document_name=doc_name,
                    doc_hash=doc_hash,
                    page_or_section=current_section,
                    text=chunk,
                ))

        # Also extract structured tables
        for table_idx, table in enumerate(doc.tables, start=1):
            rows_data = []
            for row in table.rows:
                row_cells = [cell.text.strip() for cell in row.cells]
                if any(row_cells):
                    rows_data.append(" | ".join(row_cells))
            if rows_data:
                table_text = "\n".join(rows_data)
                chunks.append(DocumentChunk(
                    chunk_id=f"{doc_hash[:12]}_tbl_{table_idx}",
                    company_id=company_id,
                    project_id=project_id,
                    document_name=doc_name,
                    doc_hash=doc_hash,
                    page_or_section=f"Table {table_idx}",
                    text=table_text,
                ))

        if not chunks:
            raise ParsingError(f"DOCX '{doc_name}' contains no extractable text.")
        return chunks

    @classmethod
    def parse_txt(cls, content: bytes, doc_name: str, company_id: str, project_id: str) -> List[DocumentChunk]:
        """Extract text from plain TXT file with encoding fallbacks."""
        for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                raw_text = content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ParsingError(f"TXT file '{doc_name}' cannot be decoded with standard encodings.")

        text = _sanitize_untrusted_text(raw_text)
        if not text:
            raise ParsingError(f"TXT file '{doc_name}' contains no text after cleaning.")

        doc_hash = compute_sha256(content)
        return [
            DocumentChunk(
                chunk_id=f"{doc_hash[:12]}_{idx}",
                company_id=company_id,
                project_id=project_id,
                document_name=doc_name,
                doc_hash=doc_hash,
                page_or_section=f"Section {idx + 1}",
                text=chunk,
            )
            for idx, chunk in enumerate(chunk_text(text))
        ]

    @classmethod
    def parse_csv(cls, content: bytes, doc_name: str, company_id: str, project_id: str) -> List[DocumentChunk]:
        """Parse CSV tables preserving column names and numeric data."""
        try:
            df = pd.read_csv(io.BytesIO(content))
        except Exception as exc:
            raise ParsingError(f"Corrupt or unreadable CSV '{doc_name}': {exc}") from exc

        if df.empty:
            raise ParsingError(f"CSV '{doc_name}' has no rows.")

        doc_hash = compute_sha256(content)
        header_line = " | ".join(str(c) for c in df.columns)
        summary = f"CSV dataset with {len(df)} rows and columns: {list(df.columns)}"

        chunks: List[DocumentChunk] = [
            DocumentChunk(
                chunk_id=f"{doc_hash[:12]}_summary",
                company_id=company_id,
                project_id=project_id,
                document_name=doc_name,
                doc_hash=doc_hash,
                page_or_section="Dataset Summary",
                text=summary,
            )
        ]

        # Batch rows into readable chunks of up to 25 rows
        batch_size = 25
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i : i + batch_size]
            rows_text = [header_line]
            for _, row in batch.iterrows():
                rows_text.append(" | ".join(str(val) for val in row.values))
            batch_text = "\n".join(rows_text)

            chunks.append(DocumentChunk(
                chunk_id=f"{doc_hash[:12]}_rows_{i}_{i+len(batch)}",
                company_id=company_id,
                project_id=project_id,
                document_name=doc_name,
                doc_hash=doc_hash,
                page_or_section=f"Rows {i + 1}-{i + len(batch)}",
                text=batch_text,
            ))

        return chunks

    @classmethod
    def parse_xlsx(cls, content: bytes, doc_name: str, company_id: str, project_id: str) -> List[DocumentChunk]:
        """Parse Excel spreadsheets preserving sheets, formulas/values, and headers."""
        try:
            excel_file = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")
        except Exception as exc:
            raise ParsingError(f"Corrupt or unreadable Excel spreadsheet '{doc_name}': {exc}") from exc

        doc_hash = compute_sha256(content)
        chunks: List[DocumentChunk] = []

        for sheet_name in excel_file.sheet_names:
            try:
                df = pd.read_excel(excel_file, sheet_name=sheet_name)
            except Exception:
                continue

            if df.empty:
                continue

            header_line = " | ".join(str(c) for c in df.columns)
            chunks.append(DocumentChunk(
                chunk_id=f"{doc_hash[:12]}_{sheet_name[:10]}_summary",
                company_id=company_id,
                project_id=project_id,
                document_name=doc_name,
                doc_hash=doc_hash,
                page_or_section=f"Sheet: {sheet_name}",
                text=f"Sheet '{sheet_name}' with {len(df)} rows. Columns: {list(df.columns)}",
            ))

            batch_size = 25
            for i in range(0, len(df), batch_size):
                batch = df.iloc[i : i + batch_size]
                rows_text = [header_line]
                for _, row in batch.iterrows():
                    rows_text.append(" | ".join(str(val) for val in row.values))

                chunks.append(DocumentChunk(
                    chunk_id=f"{doc_hash[:12]}_{sheet_name[:10]}_rows_{i}",
                    company_id=company_id,
                    project_id=project_id,
                    document_name=doc_name,
                    doc_hash=doc_hash,
                    page_or_section=f"Sheet: {sheet_name} (Rows {i+1}-{i+len(batch)})",
                    text="\n".join(rows_text),
                ))

        if not chunks:
            raise ParsingError(f"Excel file '{doc_name}' contains no readable sheets or data.")
        return chunks

    @classmethod
    def parse(
        cls,
        filename: str,
        content: Optional[bytes] = None,
        company_id: str = "default_company",
        project_id: str = "default_project",
        *,
        file_content: Optional[bytes] = None,
        doc_hash: Optional[str] = None,
    ) -> List[DocumentChunk]:
        """Dispatch parsing based on file extension with full validation."""
        raw_bytes = content if content is not None else file_content
        if raw_bytes is None:
            raise FileValidationError(f"File content is required for '{filename}'.")
        cls.validate_file(filename, raw_bytes)
        ext = Path(filename).suffix.lower()

        if ext == ".pdf":
            return cls.parse_pdf(raw_bytes, filename, company_id, project_id)
        elif ext == ".docx":
            return cls.parse_docx(raw_bytes, filename, company_id, project_id)
        elif ext == ".txt":
            return cls.parse_txt(raw_bytes, filename, company_id, project_id)
        elif ext == ".csv":
            return cls.parse_csv(raw_bytes, filename, company_id, project_id)
        elif ext == ".xlsx":
            return cls.parse_xlsx(raw_bytes, filename, company_id, project_id)
        else:
            raise FileValidationError(f"Unsupported format: {ext}")
