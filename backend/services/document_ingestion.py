import base64
import binascii
import logging
from io import BytesIO

logger = logging.getLogger(__name__)


class DocumentExtractionError(Exception):
    pass


def is_pdf(filename: str | None, content_type: str | None) -> bool:
    return (
        (content_type or "").split(";")[0].strip().lower() == "application/pdf"
        or (filename or "").strip().lower().endswith(".pdf")
    )


def _strip_data_url(value: str) -> str:
    if value.startswith("data:") and "," in value:
        return value.split(",", 1)[1]
    return value


def decode_content_bytes(content: str, content_encoding: str | None = None) -> bytes:
    value = content or ""
    encoding = (content_encoding or "").strip().lower()

    if encoding == "base64" or value.startswith("data:"):
        try:
            return base64.b64decode(_strip_data_url(value), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise DocumentExtractionError("Uploaded document content is not valid base64") from exc

    return value.encode("utf-8")


def extract_pdf_text(content: str, content_encoding: str | None = None) -> tuple[str, int]:
    if content_encoding == "base64" or (content or "").startswith("data:"):
        pdf_bytes = decode_content_bytes(content, content_encoding)
    else:
        # Backward compatibility for older clients that sent PDF bytes through readAsText.
        pdf_bytes = (content or "").encode("latin-1", errors="ignore")

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DocumentExtractionError("PDF text extraction dependency is not installed") from exc

    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=False)
        if reader.is_encrypted:
            try:
                decrypt_result = reader.decrypt("")
            except Exception as exc:
                raise DocumentExtractionError("Encrypted PDFs are not supported unless they can be opened without a password") from exc
            if not decrypt_result:
                raise DocumentExtractionError("Encrypted PDFs are not supported unless they can be opened without a password")

        page_count = len(reader.pages)
        pages = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                logger.warning(
                    "PDF page text extraction failed page=%s error=%s",
                    page_number,
                    str(exc)[:300],
                )
                text = ""
            text = text.strip()
            if text:
                pages.append(f"Page {page_number}\n{text}")
    except Exception as exc:
        raise DocumentExtractionError("Could not extract readable text from PDF") from exc

    extracted_text = "\n\n".join(pages).strip()
    if not extracted_text:
        raise DocumentExtractionError(
            "PDF has no extractable text. Scanned/image-only PDFs need OCR before upload."
        )

    logger.info(
        "knowledge_ingestion extractor=pdf input_bytes=%s page_count=%s extracted_chars=%s readable_pages=%s",
        len(pdf_bytes),
        page_count,
        len(extracted_text),
        len(pages),
    )
    return extracted_text, len(pdf_bytes)


def extract_document_text(
    filename: str,
    content_type: str | None,
    content: str,
    content_encoding: str | None = None
) -> tuple[str, int]:
    if is_pdf(filename, content_type):
        return extract_pdf_text(content, content_encoding)

    text = content or ""
    if content_encoding == "base64" or text.startswith("data:"):
        try:
            text = decode_content_bytes(text, content_encoding).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentExtractionError("Uploaded text document is not valid UTF-8") from exc

    size_bytes = len(text.encode("utf-8"))
    logger.info(
        "knowledge_ingestion extractor=text input_bytes=%s extracted_chars=%s",
        size_bytes,
        len((text or "").strip()),
    )
    return text, size_bytes
