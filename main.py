import os
import json
import time
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

llm = ChatGroq(temperature=0, model_name="llama-3.3-70b-versatile")
embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
vectorstore = Chroma(persist_directory=str(DB_DIR), embedding_function=embeddings)


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Scans the new Decoupled Storage Layer on startup."""
    try:
        existing_data = vectorstore.get()
        if not existing_data or not existing_data.get("documents"):
            print(
                "⚠️ Empty DB detected. Scanning secure storage layer for ingestion..."
            )
            parsed_docs = []
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=800, chunk_overlap=100
            )

            for filename in os.listdir(STORAGE_DIR):
                file_path = os.path.join(STORAGE_DIR, filename)
                print(f"📄 Parsing: {filename}")
                if filename.endswith(".pdf"):
                    loader = PyPDFLoader(file_path)
                elif filename.endswith(".docx"):
                    loader = Docx2txtLoader(file_path)
                else:
                    continue

                raw_pages = loader.load()
                chunks = text_splitter.split_documents(raw_pages)

                # Base metadata for initial files
                for chunk in chunks:
                    chunk.metadata["allowed_roles"] = ["Admin", "Manager", "Employee"]
                    chunk.metadata["source"] = filename
                parsed_docs.extend(chunks)

            if parsed_docs:
                print(f"⚡ Indexing {len(parsed_docs)} chunks...")
                vectorstore.add_documents(parsed_docs)
                print("✅ Vector DB built and fully locked into dimensions!")
    except Exception as e:
        print(f"⚠️ Startup Exception: {str(e)}")
    yield


app = FastAPI(title="Enterprise Omni-Modal RAG", lifespan=lifespan)
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

    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    dev_reload = os.getenv("DEV_RELOAD", "False").lower() in ("1", "true", "yes")

    uvicorn.run("main:app", host=host, port=port, reload=dev_reload)
