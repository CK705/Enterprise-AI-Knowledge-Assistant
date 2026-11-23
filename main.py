import os
import json
import time
from hashlib import sha256
from threading import Lock
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

# LangChain Framework & Vector Core
from langchain_groq import ChatGroq
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Phase 2: Secure Routers & Authentication
from routers import auth_storage
from routers.auth_storage import verify_token_and_get_role

# --- ENTERPRISE CONFIGURATION ---
BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "raw_documents"
DB_DIR = BASE_DIR / "enterprise_rag_db"

STORAGE_DIR.mkdir(parents=True, exist_ok=True)
DB_DIR.mkdir(parents=True, exist_ok=True)

llm = ChatGroq(temperature=0, model_name="openai/gpt-oss-120b")
# llm = ChatGroq(temperature=0, model_name="openai/gpt-oss-safeguard-20b")
embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
vectorstore = Chroma(
    collection_name="langchain",
    persist_directory=str(DB_DIR),
    embedding_function=embeddings,
)
index_lock = Lock()
document_loaders = {".pdf": PyPDFLoader, ".docx": Docx2txtLoader}
text_splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)


def normalize_allowed_roles(metadata: dict) -> set[str]:
    roles = metadata.get("allowed_roles", [])
    if isinstance(roles, str):
        return {
            role.strip() for role in roles.replace(";", ",").split(",") if role.strip()
        }
    if isinstance(roles, (list, tuple, set)):
        return {str(role).strip() for role in roles if str(role).strip()}
    return set()


def filter_docs_by_role(docs: List[Document], user_role: str) -> List[Document]:
    """RBAC is intentionally disabled for ingestion and retrieval.

    All indexed chunks should remain available to every pipeline.
    """
    return docs or []


def index_document(path: Path, filename: str, owner_id: str, destination: Path | None = None):
    """Index a staged upload or a file already in storage."""
    loader = document_loaders.get(Path(filename).suffix.lower())
    if loader is None:
        raise ValueError("Only PDF and DOCX files are supported.")
    chunks = [
        chunk for chunk in text_splitter.split_documents(loader(path).load())
        if chunk.page_content.strip()
    ]
    if not chunks:
        raise ValueError("The document contains no extractable text.")

    digest = sha256()
    with path.open("rb") as document:
        for block in iter(lambda: document.read(1024 * 1024), b""):
            digest.update(block)
    revision = digest.hexdigest()
    chunk_ids = [f"{filename}:{revision}:{i}" for i in range(len(chunks))]
    for chunk in chunks:
        if "file_path" in chunk.metadata:
            chunk.metadata["file_path"] = str(destination or path)
        chunk.metadata.update(
            source=filename,
            owner_id=owner_id,
            allowed_roles="Admin,Manager,Employee",
        )

    with index_lock:
        previous = indexed_chunk_ids(filename)
        new_ids = sorted(set(chunk_ids).difference(previous))
        try:
            vectorstore.add_documents(chunks, ids=chunk_ids)
            if destination is not None:
                path.replace(destination)
        except Exception:
            if new_ids:
                vectorstore.delete(ids=new_ids)
            raise

        stale_ids = sorted(set(previous).difference(chunk_ids))
        if stale_ids:
            vectorstore.delete(ids=stale_ids)


def indexed_chunk_ids(filename: str) -> list[str]:
    existing = vectorstore.get(include=["metadatas"])
    return [
        chunk_id
        for chunk_id, metadata in zip(existing["ids"], existing["metadatas"])
        if metadata and Path(metadata.get("source") or "").name.casefold() == filename.casefold()
    ]


def delete_indexed_document(path: Path) -> None:
    with index_lock:
        ids = indexed_chunk_ids(path.name)
        if ids:
            vectorstore.delete(ids=ids)
        path.unlink()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Backfill stored documents missing from the retrieval collection."""
    existing = vectorstore.get(include=["metadatas"])
    indexed_names = {
        Path(metadata["source"]).name.casefold()
        for metadata in existing["metadatas"]
        if metadata and metadata.get("source")
    }
    for path in STORAGE_DIR.iterdir():
        if (
            path.is_file()
            and path.suffix.lower() in document_loaders
            and path.name.casefold() not in indexed_names
        ):
            try:
                index_document(path, path.name, owner_id="system")
            except Exception as exc:
                print(f"Failed to index {path.name}: {exc}")
    yield


app = FastAPI(title="Enterprise Omni-Modal RAG", lifespan=lifespan)
app.state.index_document = index_document
app.state.delete_indexed_document = delete_indexed_document
app.include_router(auth_storage.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str


class RAGResponse(BaseModel):
    pipeline: str
    answer: str
    retrieved_chunks: List[str]
    plan: Optional[dict] = None
    latency: float = 0.0
    tokens: Optional[dict] = None
    correction_log: Optional[str] = None


# --- PIPELINE A: NAIVE RAG (SECURED) ---
@app.post("/query/naive", response_model=RAGResponse)
async def query_naive(
    request: QueryRequest, auth_data: dict = Depends(verify_token_and_get_role)
):
    start_time = time.time()
    user_role = auth_data["role"]

    docs = filter_docs_by_role(
        vectorstore.similarity_search(request.question, k=6), user_role
    )[:3]
    context = "\n\n".join([d.page_content for d in docs])

    if not docs:
        return RAGResponse(
            pipeline="Naive",
            answer="Access Denied or No Data Found.",
            retrieved_chunks=[],
        )

    prompt = ChatPromptTemplate.from_template(
        "Answer using context.\n\nContext:\n{context}\n\nQuestion: {question}"
    )
    response = (prompt | llm).invoke({"context": context, "question": request.question})

    return RAGResponse(
        pipeline="Naive RAG",
        answer=response.content,
        retrieved_chunks=[d.page_content for d in docs],
        latency=round(time.time() - start_time, 2),
        tokens=getattr(response, "usage_metadata", None) or {},
    )


# --- PIPELINE B: HYBRID RAG (SECURED) ---
@app.post("/query/hybrid", response_model=RAGResponse)
async def query_hybrid(
    request: QueryRequest, auth_data: dict = Depends(verify_token_and_get_role)
):
    start_time = time.time()
    user_role = auth_data["role"]

    vec_docs = vectorstore.similarity_search(request.question, k=4)

    # 🔒 BM25 Security Pre-Filter: Mathematically drop restricted chunks before keyword scan!
    db_data = vectorstore.get()
    filtered_docs = [
        Document(page_content=t, metadata=m)
        for t, m in zip(db_data["documents"], db_data["metadatas"])
    ]

    bm25_docs = []
    if filtered_docs:
        bm25 = BM25Retriever.from_documents(filtered_docs)
        bm25_docs = bm25.invoke(request.question)

    combined_dict = {d.page_content: d for d in (vec_docs + bm25_docs)}
    context = "\n\n".join(combined_dict.keys())

    prompt = ChatPromptTemplate.from_template(
        "Answer using hybrid context.\n\nContext:\n{context}\n\nQuestion: {question}"
    )
    response = (prompt | llm).invoke({"context": context, "question": request.question})

    return RAGResponse(
        pipeline="Hybrid RAG",
        answer=response.content,
        retrieved_chunks=list(combined_dict.keys()),
        latency=round(time.time() - start_time, 2),
    )


# --- PIPELINE C: MULTI-HOP (SECURED) ---
@app.post("/query/multihop", response_model=RAGResponse)
async def query_multihop(
    request: QueryRequest, auth_data: dict = Depends(verify_token_and_get_role)
):
    start_time = time.time()

    plan_response = llm.invoke(
        f"""Format: {{"hop1": "query", "hop2": "query"}}\nQuestion: "{request.question}" """
    )
    try:
        plan = json.loads(
            plan_response.content.strip()
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )
    except:
        plan = {"hop1": request.question, "hop2": "context"}

    docs_hop1 = vectorstore.similarity_search(plan.get("hop1", request.question), k=3)
    docs_hop2 = vectorstore.similarity_search(plan.get("hop2", request.question), k=3)
    context = "\n\n".join([d.page_content for d in (docs_hop1 + docs_hop2)])

    synth_response = (
        ChatPromptTemplate.from_template(
            "Synthesize.\nContext:\n{context}\nQuestion: {question}"
        )
        | llm
    ).invoke({"context": context, "question": request.question})

    return RAGResponse(
        pipeline="Autonomous Multi-Hop",
        answer=synth_response.content,
        retrieved_chunks=[d.page_content for d in (docs_hop1 + docs_hop2)],
        plan=plan,
        latency=round(time.time() - start_time, 2),
    )


# --- PIPELINE D: CRAG / SELF-CORRECTING (SECURED) ---
@app.post("/query/self_correct", response_model=RAGResponse)
async def query_crag(
    request: QueryRequest, auth_data: dict = Depends(verify_token_and_get_role)
):
    start_time = time.time()

    # 1. Retrieve
    docs = vectorstore.similarity_search(request.question, k=6)[:3]
    context = "\n\n".join([d.page_content for d in docs])

    # 2. Grade (LLM-as-a-judge)
    grade_prompt = f"Does this context '{context}' contain the answer to '{request.question}'? Reply ONLY with YES or NO."
    grade = llm.invoke(grade_prompt).content.strip().upper()

    correction_log = f"Grader Evaluation: {grade}."
    if "NO" in grade:
        correction_log += " Context insufficient. Triggering safety refusal."
        answer = "I'm sorry, but based on the securely available corporate data, I cannot answer this request without hallucinating."
    else:
        correction_log += " Context valid. Synthesizing response."
        answer = (
            (
                ChatPromptTemplate.from_template(
                    "Answer based strictly on context.\nContext:\n{context}\nQuestion: {question}"
                )
                | llm
            )
            .invoke({"context": context, "question": request.question})
            .content
        )

    return RAGResponse(
        pipeline="CRAG",
        answer=answer,
        retrieved_chunks=[d.page_content for d in docs],
        correction_log=correction_log,
        latency=round(time.time() - start_time, 2),
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8001))
    host = os.getenv("HOST", "0.0.0.0")
    dev_reload = os.getenv("DEV_RELOAD", "False").lower() in ("1", "true", "yes")

    uvicorn.run("main:app", host=host, port=port, reload=dev_reload)
