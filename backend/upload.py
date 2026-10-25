import os
import tempfile

import chromadb

from utils import (
    load_pdf,
    create_chunks,
    get_gemini_client,
    create_embeddings
)

from config import (
    CHROMA_PATH,
    COLLECTION_NAME,
    CHUNK_SIZE,
    CHUNK_OVERLAP
)


def process_uploaded_pdf(pdf_file, api_key: str = None, provider: str = "Gemini"):
    """
    Process an uploaded PDF and store its
    chunks + embeddings in ChromaDB using user-provided Gemini API key.
    """

    if not api_key or not str(api_key).strip():
        raise ValueError("API key is required. Please provide your free Gemini API key.")

    # ---------------------------------
    # Save uploaded PDF temporarily
    # ---------------------------------

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf"
    ) as temp_file:

        temp_file.write(pdf_file)

        temp_pdf_path = temp_file.name


    try:

        # ---------------------------------
        # Create client & extract text
        # ---------------------------------
        client = get_gemini_client(api_key=api_key)
        text = load_pdf(temp_pdf_path, client=client, api_key=api_key)

        if not text or not text.strip():
            raise ValueError(
                "Could not extract readable text from this PDF. "
                "If this document is a scanned image or photo, please verify that your "
                "Gemini API key is valid to enable AI OCR transcription, or upload a "
                "text-searchable PDF."
            )

        # ---------------------------------
        # Create chunks
        # ---------------------------------

        chunks = create_chunks(
            text,
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP
        )

        if not chunks:
            raise ValueError("No text chunks could be created from the PDF.")

        # ---------------------------------
        # Generate embeddings
        # ---------------------------------
        embeddings = create_embeddings(client, chunks)


        # ---------------------------------
        # Connect to ChromaDB
        # ---------------------------------

        chroma_client = chromadb.PersistentClient(
            path=CHROMA_PATH
        )


        # ---------------------------------
        # Reset & Recreate collection cleanly
        # ---------------------------------

        try:
            chroma_client.delete_collection(
                name=COLLECTION_NAME
            )
        except Exception:
            pass

        collection = chroma_client.create_collection(
            name=COLLECTION_NAME
        )


        # ---------------------------------
        # Store new document
        # ---------------------------------

        collection.add(

            ids=[
                f"chunk_{i}"
                for i in range(len(chunks))
            ],

            documents=chunks,

            embeddings=embeddings,

            metadatas=[
                {
                    "source": "uploaded_pdf"
                }
                for _ in chunks
            ]
        )


        return {
            "success": True,
            "chunks": len(chunks)
        }


    finally:

        # ---------------------------------
        # Delete temporary PDF
        # ---------------------------------

        if os.path.exists(temp_pdf_path):

            os.remove(temp_pdf_path)