import chromadb

from utils import (
    get_gemini_client,
    create_query_embedding
)

from config import (
    GEMINI_MODEL,
    CHROMA_PATH,
    COLLECTION_NAME,
    TOP_K
)


def ask_question(question: str, api_key: str = None, provider: str = "Gemini"):
    """
    Retrieves context from ChromaDB and generates an answer using
    user-provided Gemini API key.
    """

    if not api_key or not str(api_key).strip():
        return "⚠️ API key is required. Please click 'Select AI model' in the topbar or sidebar to enter your free Gemini API key."

    api_key = str(api_key).strip()

    # Connect to ChromaDB and open collection
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

    try:
        collection = chroma_client.get_collection(name=COLLECTION_NAME)
    except Exception:
        return "No document has been indexed yet. Please upload a PDF first."

    if collection.count() == 0:
        return "The document collection is empty. Please upload a PDF first."

    # Generate Query Embedding & Search Similar Chunks
    try:
        client = get_gemini_client(api_key=api_key)
        query_embedding = create_query_embedding(client, question)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=TOP_K
        )
    except Exception as e:
        err_msg = str(e)
        if "dimension" in err_msg.lower():
            return "⚠️ Embedding dimension mismatch: The document in the database was indexed using a different model. Please re-upload your PDF."
        return f"Error retrieving document context: {err_msg}"

    # Extract Retrieved Chunks
    retrieved_chunks = results.get("documents", [[]])[0]
    if not retrieved_chunks:
        return "I couldn't find any relevant sections in the provided document."

    # Build Context
    context = "\n\n".join(retrieved_chunks)

    # Generate Answer using Gemini
    prompt = f"""You are a helpful AI assistant.

Answer the user's question ONLY using the provided context.

If the answer is not available in the context, say:
"I couldn't find the answer in the provided document."

Context:
{context}

Question:
{question}

Answer:"""

    models_to_try = [GEMINI_MODEL, "gemini-3.6-flash", "gemini-2.5-flash", "gemini-1.5-pro"]
    seen = set()
    models = [m for m in models_to_try if not (m in seen or seen.add(m))]
    last_err = None
    for m in models:
        try:
            response = client.models.generate_content(
                model=m,
                contents=prompt
            )
            return response.text
        except Exception as e:
            last_err = e
    return f"Gemini API Error: {str(last_err)}"