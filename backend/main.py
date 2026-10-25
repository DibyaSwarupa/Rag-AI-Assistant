import os
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.rag import ask_question
from backend.upload import process_uploaded_pdf

load_dotenv()

app = FastAPI()


# ================================
# CORS
# ================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================================
# Question Model
# ================================

class Question(BaseModel):
    question: str
    api_key: Optional[str] = None
    provider: Optional[str] = "Gemini"


from pathlib import Path
from fastapi.staticfiles import StaticFiles

# ================================
# Health / API Status
# ================================

@app.get("/api/status")
def api_status():
    return {
        "status": "online",
        "message": "PDF RAG Chatbot API is running"
    }


# ================================
# Ask Question
# ================================

@app.post("/ask")
def ask(
    question: Question,
    x_api_key: Optional[str] = Header(None),
    x_provider: Optional[str] = Header(None)
):
    key = question.api_key or x_api_key or os.getenv("GEMINI_API_KEY")
    prov = question.provider or x_provider or "Gemini"

    if key:
        key = str(key).strip()

    answer = ask_question(
        question=question.question,
        api_key=key,
        provider=prov
    )

    return {
        "answer": answer
    }


# ================================
# Upload PDF
# ================================

@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    api_key: Optional[str] = Form(None),
    provider: Optional[str] = Form("Gemini"),
    x_api_key: Optional[str] = Header(None),
    x_provider: Optional[str] = Header(None)
):
    key = api_key or x_api_key or os.getenv("GEMINI_API_KEY")
    prov = provider or x_provider or "Gemini"

    if key:
        key = str(key).strip()

    if not file.filename.lower().endswith(".pdf"):
        return {
            "success": False,
            "message": "Only PDF files are allowed."
        }

    pdf_bytes = await file.read()

    try:
        result = process_uploaded_pdf(
            pdf_bytes,
            api_key=key,
            provider=prov
        )

        return {
            "success": True,
            "message": "PDF uploaded and processed successfully.",
            "filename": file.filename,
            "chunks": result["chunks"]
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }


# ================================
# Mount Frontend Static Files
# ================================
frontend_path = Path(__file__).resolve().parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")