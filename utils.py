# Imports
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from google import genai
from google.genai import types
from dotenv import load_dotenv
import os

from config import EMBEDDING_MODEL, GEMINI_MODEL


# ============================================================
# Read PDF and Extract Text (Multi-Layered Strategy + Vision OCR)
# ============================================================

import re

# Clean text utility
def _clean_text(val: str) -> str:
    if not val:
        return ""
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', val)
    return cleaned.strip()

# ============================================================
# Read PDF and Extract Text (Multi-Layered Strategy + Vision OCR)
# ============================================================

def load_pdf(pdf_path, client=None, api_key=None):
    """
    Reads a PDF file and returns all its text as a single string.
    Uses layered extraction strategies:
    1. PyMuPDF (fitz) - text, blocks, words, widgets, annotations, layout extraction.
    2. PyPDF - standard, layout, orientations & form fields extraction.
    3. Gemini Multimodal OCR (Direct PDF + High-res Page Rendering fallback)
       for scanned / photo / image-only PDFs.
    """
    text = ""
    ocr_error_details = []

    # Strategy 1: PyMuPDF (fitz)
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz
        except ImportError:
            fitz = None

    if fitz is not None:
        try:
            doc = fitz.open(pdf_path)
            if doc.is_encrypted:
                try:
                    doc.authenticate("")
                except Exception:
                    pass

            extracted_pages = []
            for page in doc:
                p_text = page.get_text("text", sort=True)
                
                # Check blocks if plain text yields little
                if not _clean_text(p_text):
                    blocks = page.get_text("blocks", sort=True)
                    block_texts = [_clean_text(b[4]) for b in blocks if len(b) > 4 and _clean_text(b[4])]
                    p_text = "\n".join(block_texts)

                # Check words if blocks empty
                if not _clean_text(p_text):
                    words = page.get_text("words", sort=True)
                    if words:
                        words.sort(key=lambda w: (w[1], w[0]))
                        p_text = " ".join([w[4] for w in words])

                # Extract interactive form widgets & annotations if text is sparse
                extra_items = []
                try:
                    for widget in page.widgets():
                        if widget.field_value:
                            val = str(widget.field_value).strip()
                            if val:
                                extra_items.append(val)
                except Exception:
                    pass

                try:
                    for annot in page.annots():
                        info = annot.info
                        if info and info.get("content"):
                            val = str(info["content"]).strip()
                            if val:
                                extra_items.append(val)
                except Exception:
                    pass

                if extra_items:
                    p_text = (p_text + "\n" + "\n".join(extra_items)).strip()

                cleaned_p = _clean_text(p_text)
                if cleaned_p:
                    extracted_pages.append(cleaned_p)

            doc.close()
            if extracted_pages:
                text = "\n\n".join(extracted_pages)
        except Exception as e:
            print(f"PyMuPDF extraction notice: {e}")

    # Strategy 2: PyPDF extraction if PyMuPDF yielded nothing or very little text
    if not text or len(_clean_text(text)) < 15:
        try:
            reader = PdfReader(pdf_path, strict=False)
            if reader.is_encrypted:
                try:
                    reader.decrypt("")
                except Exception:
                    pass

            pypdf_pages = []
            for page in reader.pages:
                try:
                    p_text = page.extract_text(orientations=(0, 90, 180, 270))
                    cleaned_p = _clean_text(p_text)
                    if cleaned_p:
                        pypdf_pages.append(cleaned_p)
                except Exception:
                    pass

            # Extract PyPDF form fields if available
            try:
                fields = reader.get_fields()
                if fields:
                    field_vals = []
                    for f_name, f_val in fields.items():
                        if isinstance(f_val, dict) and f_val.get('/V'):
                            field_vals.append(f"{f_name}: {f_val.get('/V')}")
                    if field_vals:
                        pypdf_pages.append("\n".join(field_vals))
            except Exception:
                pass

            if pypdf_pages:
                combined_pypdf = "\n\n".join(pypdf_pages)
                if len(_clean_text(combined_pypdf)) > len(_clean_text(text)):
                    text = combined_pypdf
        except Exception as e:
            print(f"PyPDF extraction notice: {e}")

    cleaned_final = _clean_text(text)
    if cleaned_final and len(cleaned_final) >= 15:
        return cleaned_final

    # Strategy 3: Scanned / Image-based PDF fallback using Gemini Multimodal OCR
    ocr_client = client
    if ocr_client is None:
        gemini_key_candidate = api_key
        if not gemini_key_candidate:
            load_dotenv()
            gemini_key_candidate = os.getenv("GEMINI_API_KEY")

        if gemini_key_candidate:
            try:
                ocr_client = get_gemini_client(api_key=gemini_key_candidate)
            except Exception as client_err:
                ocr_error_details.append(f"Gemini client init: {client_err}")
        else:
            ocr_error_details.append("No Gemini API key provided for OCR fallback.")

    if ocr_client is not None:
        models_to_try = [GEMINI_MODEL, "gemini-3.6-flash", "gemini-2.5-flash", "gemini-1.5-pro"]
        seen = set()
        ocr_models = [m for m in models_to_try if not (m in seen or seen.add(m))]

        # Method 3A: Whole PDF document OCR
        try:
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            for model_name in ocr_models:
                try:
                    response = ocr_client.models.generate_content(
                        model=model_name,
                        contents=[
                            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                            "Extract and transcribe all text, headings, tables, numbers, and data from this PDF document into clean readable plain text."
                        ]
                    )
                    if response and response.text:
                        ocr_txt = _clean_text(response.text)
                        if len(ocr_txt) >= 5:
                            return ocr_txt
                except Exception as model_err:
                    ocr_error_details.append(f"Model {model_name} PDF OCR error: {model_err}")
        except Exception as file_err:
            ocr_error_details.append(f"File read error: {file_err}")

        # Method 3B: Per-page Image Rendering & Vision OCR
        try:
            import pymupdf as fitz
            doc = fitz.open(pdf_path)
            rendered_pages_text = []
            for page_idx, page in enumerate(doc):
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("jpeg", jpg_quality=85)
                page_text_found = False
                for model_name in ocr_models:
                    try:
                        response = ocr_client.models.generate_content(
                            model=model_name,
                            contents=[
                                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                                f"Transcribe all readable text, labels, numbers, tables and contents from page {page_idx + 1} accurately into plain text."
                            ]
                        )
                        if response and response.text:
                            p_ocr = _clean_text(response.text)
                            if p_ocr:
                                rendered_pages_text.append(p_ocr)
                                page_text_found = True
                                break
                    except Exception as img_err:
                        ocr_error_details.append(f"Page {page_idx + 1} OCR ({model_name}): {img_err}")
                if not page_text_found:
                    pass
            doc.close()
            if rendered_pages_text:
                return "\n\n".join(rendered_pages_text).strip()
        except Exception as render_err:
            ocr_error_details.append(f"Image render OCR error: {render_err}")

    if ocr_error_details:
        print("OCR fallback diagnostic details:", " | ".join(ocr_error_details))

    return _clean_text(text)


# ============================================================
# Split Text into Chunks
# ============================================================

def create_chunks(text, chunk_size=1000, chunk_overlap=200):
    """
    Splits the given text into smaller overlapping chunks.
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )
    chunks = text_splitter.split_text(text)
    return chunks


# ============================================================
# Create Gemini Client
# ============================================================

def get_gemini_client(api_key=None):
    """
    Creates and returns a Gemini client using user-supplied API key
    or environment variable. Raises ValueError if no key is found.
    """
    if not api_key:
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")

    if not api_key or not str(api_key).strip():
        raise ValueError(
            "Gemini API key is required. Please enter your free API key in the AI model settings."
        )

    # Create Gemini client
    client = genai.Client(
        api_key=str(api_key).strip()
    )

    return client


# ============================================================
# Generate Embeddings (with Batching & Fallback)
# ============================================================

def create_embeddings(client, chunks, batch_size=50):
    """
    Generates embeddings for all chunks and
    returns a list of embedding vectors.
    """
    all_embeddings = []
    models_to_try = [EMBEDDING_MODEL, "text-embedding-004", "gemini-embedding-001"]
    seen = set()
    models = [m for m in models_to_try if not (m in seen or seen.add(m))]

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        batch_embedded = False
        last_err = None
        for model_name in models:
            try:
                response = client.models.embed_content(
                    model=model_name,
                    contents=batch
                )
                embeddings = [
                    embedding.values
                    for embedding in response.embeddings
                ]
                all_embeddings.extend(embeddings)
                batch_embedded = True
                break
            except Exception as e:
                last_err = e

        if not batch_embedded:
            raise RuntimeError(f"Failed to generate embeddings: {last_err}")

    return all_embeddings


# ============================================================
# Generate Query Embedding (with Fallback)
# ============================================================

def create_query_embedding(client, question):
    """
    Generates an embedding for the user's question.
    """
    models_to_try = [EMBEDDING_MODEL, "text-embedding-004", "gemini-embedding-001"]
    seen = set()
    models = [m for m in models_to_try if not (m in seen or seen.add(m))]
    last_err = None

    for model_name in models:
        try:
            response = client.models.embed_content(
                model=model_name,
                contents=question
            )
            return response.embeddings[0].values
        except Exception as e:
            last_err = e

    raise RuntimeError(f"Failed to generate query embedding: {last_err}")