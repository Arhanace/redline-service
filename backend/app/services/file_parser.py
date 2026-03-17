import io
from docx import Document as DocxDocument
import pdfplumber


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract plain text from a .docx file. Very fast — instant for most docs."""
    doc = DocxDocument(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract plain text from a PDF file.

    Note: pdfplumber is slow on scanned-image PDFs (~5s per page).
    Text-based PDFs extract instantly. For production, PyMuPDF (fitz)
    would be 100x faster but requires native dependencies.
    """
    pages = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text and len(text.strip()) > 10:
                pages.append(text)
    if not pages:
        raise ValueError("Could not extract text from PDF. The file may contain only scanned images.")
    return "\n\n".join(pages)


def extract_text(filename: str, file_bytes: bytes) -> str:
    """Extract text based on file extension."""
    lower = filename.lower()
    if lower.endswith(".docx"):
        return extract_text_from_docx(file_bytes)
    elif lower.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    elif lower.endswith(".txt"):
        return file_bytes.decode("utf-8")
    else:
        raise ValueError(f"Unsupported file type: {filename}. Supported: .docx, .pdf, .txt")
