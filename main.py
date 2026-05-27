import os
import json
import time
from contextlib import asynccontextmanager
from urllib import response
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from langchain_groq import ChatGroq
from dotenv import load_dotenv

load_dotenv()

# LangChain Framework & Vector Core
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Document Parsers
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

#
# Model Initializations
# llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0, max_retries=6)
llm = ChatGroq(temperature=0, model_name="llama-3.3-70b-versatile")
embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")


db_dir = r"D:\Enterprise_RAG\enterprise_rag_db"
vectorstore = Chroma(persist_directory=db_dir, embedding_function=embeddings)


# --- AUTOMATIC DATASET INGESTION CORE (WITH BATCHING) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern FastAPI startup lifecycle manager. Handles batched ingestion."""
    try:
        existing_data = vectorstore.get()
        if not existing_data or not existing_data.get("documents"):
            print("⚠️ Empty DB detected. Initializing Real Document Ingestion...")

            source_files = [
                {"path": "financial_report_fy2024.pdf", "type": "pdf"},
                {"path": "hr_policy_manual.docx", "type": "docx"},
                {"path": "company_overview.pdf", "type": "pdf"},
                {"path": "marketing_strategy_fy2025.pdf", "type": "pdf"},
            ]

            parsed_docs = []
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=800, chunk_overlap=100
            )

            for file in source_files:
                file_path = os.path.join(r"D:\Enterprise_RAG", file["path"])
                if os.path.exists(file_path):
                    print(f"📄 Parsing: {file['path']}")
                    if file["type"] == "pdf":
                        loader = PyPDFLoader(file_path)
                    else:
                        loader = Docx2txtLoader(file_path)

                    raw_pages = loader.load()
                    chunks = text_splitter.split_documents(raw_pages)
                    parsed_docs.extend(chunks)

            if parsed_docs:
                print(
                    f"⚡ Indexing {len(parsed_docs)} chunks in slow batches to respect Free Tier API limits..."
                )

                # BATCHING LOGIC: Send 15 chunks at a time, then sleep for 3 seconds
                batch_size = 15
                for i in range(0, len(parsed_docs), batch_size):
                    batch = parsed_docs[i : i + batch_size]
                    vectorstore.add_documents(batch)
                    print(
                        f"   -> Successfully embedded batch {i//batch_size + 1} / {(len(parsed_docs)//batch_size) + 1}"
                    )
                    time.sleep(3)  # The magic pause that prevents the 429 error

                print("✅ Vector DB built and fully locked into dimensions!")
    except Exception as e:
        print(f"⚠️ Startup Ingestion Pipeline Exception: {str(e)}")

    yield  # Hand control back to FastAPI to start accepting web requests


# Initialize FastAPI with the new lifespan
app = FastAPI(title="Autonomous Enterprise RAG Assistant", lifespan=lifespan)

# Permissive CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str


# NEW: Added latency float to the response model
class RAGResponse(BaseModel):
    pipeline: str
    answer: str
    retrieved_chunks: List[str]
    plan: Optional[dict] = None
    latency: float = 0.0
    tokens: Optional[dict] = None
    correction_log: Optional[str] = None


@app.get("/")
async def health_check():
    return {"status": "healthy"}


# --- PIPELINE A: NAIVE RAG ---
@app.post("/query/naive", response_model=RAGResponse)
async def query_naive(request: QueryRequest):
    start_time = time.time()
    try:
        docs = vectorstore.similarity_search(request.question, k=3)
        context = "\n\n".join([d.page_content for d in docs])

        prompt = ChatPromptTemplate.from_template(
            "Answer the question using ONLY the provided context. If you don't know, say 'I don't know'.\n\nContext:\n{context}\n\nQuestion: {question}"
        )

        # 1. Remove StrOutputParser() to keep the rich metadata
        chain = prompt | llm

        # 2. Invoke gets an AIMessage object now, not just a string
        response = chain.invoke({"context": context, "question": request.question})

        # 3. Extract the answer string and the token math
        answer = response.content
        token_usage = getattr(response, "usage_metadata", None) or {}

        latency = round(time.time() - start_time, 2)

        return RAGResponse(
            pipeline="Naive RAG",
            answer=answer,
            retrieved_chunks=[d.page_content for d in docs],
            latency=latency,
            tokens=token_usage,  # <-- NEW: Pass the tokens to the frontend
        )
    except Exception as e:
        print(f"\n❌ PIPELINE A CRASHED: {repr(e)}\n")
        raise HTTPException(status_code=500, detail=str(e))


# --- PIPELINE B: HYBRID RAG ---
@app.post("/query/hybrid", response_model=RAGResponse)
async def query_hybrid(request: QueryRequest):
    start_time = time.time()
    try:
        db_data = vectorstore.get()
        all_docs = [
            Document(page_content=t, metadata=m)
            for t, m in zip(db_data["documents"], db_data["metadatas"])
        ]
        bm25 = BM25Retriever.from_documents(all_docs)

        vec_docs = vectorstore.similarity_search(request.question, k=2)
        bm25_docs = bm25.invoke(request.question)

        combined_dict = {d.page_content: d for d in (vec_docs + bm25_docs)}
        context = "\n\n".join([d.page_content for d in combined_dict.values()])

        prompt = ChatPromptTemplate.from_template(
            "Answer using this hybrid context. If you don't know, say 'I don't know'.\n\nContext:\n{context}\n\nQuestion: {question}"
        )

        # 1. Remove StrOutputParser()
        chain = prompt | llm

        # 2. Invoke gets an AIMessage object
        response = chain.invoke({"context": context, "question": request.question})

        # 3. Extract the answer string and the token math
        answer = response.content
        token_usage = getattr(response, "usage_metadata", None) or {}

        latency = round(time.time() - start_time, 2)
        return RAGResponse(
            pipeline="Hybrid RAG",
            answer=answer,
            retrieved_chunks=list(combined_dict.keys()),
            latency=latency,
            tokens=token_usage,  # <-- Pass tokens to React
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- PIPELINE C: AUTONOMOUS MULTI-HOP RAG ---
@app.post("/query/multihop", response_model=RAGResponse)
async def query_multihop(request: QueryRequest):
    start_time = time.time()
    try:
        planner_prompt = f"""
        Analyze this question for a corporate search engine. 
        
        CRITICAL RULES:
        1. If it is a simple name or fact lookup (e.g., "Who is X?"), make "hop1" the exact name, and make "hop2" a safe, related corporate keyword (like "role", "title", or "responsibilities"). DO NOT invent terms like "biography" or "profile".
        2. If it is a complex question comparing multiple things, break it down into two distinct search queries.

        Question: "{request.question}"
        
        Return ONLY valid JSON with exactly two keys: "hop1" and "hop2". Do not use markdown wrappers.
        Format: {{"hop1": "first keyword query", "hop2": "second keyword query"}}
        """

        # STAGE 1: PLANNER
        plan_response = llm.invoke(planner_prompt)
        plan_raw = plan_response.content.strip()

        # CRASH-PROOF TOKEN EXTRACTION 1
        plan_meta = getattr(plan_response, "usage_metadata", None) or {}

        if plan_raw.startswith("```"):
            plan_raw = plan_raw.replace("```json", "").replace("```", "").strip()
        plan = json.loads(plan_raw)

        docs_hop1 = vectorstore.similarity_search(
            plan.get("hop1", request.question), k=2
        )
        docs_hop2 = vectorstore.similarity_search(
            plan.get("hop2", request.question), k=2
        )

        context = "\n\n".join(
            [f"[Fact Group A]: {d.page_content}" for d in docs_hop1]
            + [f"[Fact Group B]: {d.page_content}" for d in docs_hop2]
        )

        reasoning_prompt = ChatPromptTemplate.from_template(
            "You are a Senior Strategic Analyst. Synthesize these disjoint facts to solve the user prompt step-by-step. Show all your calculations.\n\nContext:\n{context}\n\nQuestion: {question}"
        )

        # STAGE 2: SYNTHESIS
        chain = reasoning_prompt | llm
        synth_response = chain.invoke(
            {"context": context, "question": request.question}
        )
        answer = synth_response.content

        # CRASH-PROOF TOKEN EXTRACTION 2
        synth_meta = getattr(synth_response, "usage_metadata", None) or {}

        # STAGE 3: COST CALCULATION
        total_tokens = {
            "input_tokens": plan_meta.get("input_tokens", 0)
            + synth_meta.get("input_tokens", 0),
            "output_tokens": plan_meta.get("output_tokens", 0)
            + synth_meta.get("output_tokens", 0),
        }

        retrieved_logs = [f"Generated Search Plan -> {json.dumps(plan)}"] + [
            d.page_content for d in (docs_hop1 + docs_hop2)
        ]

        latency = round(time.time() - start_time, 2)
        return RAGResponse(
            pipeline="Autonomous Multi-Hop RAG",
            answer=answer,
            retrieved_chunks=retrieved_logs,
            plan=plan,
            latency=latency,
            tokens=total_tokens,  # <-- Sent safely to React!
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- PIPELINE D: SELF-CORRECTING RAG (CRAG) ---
@app.post("/query/self_correct", response_model=RAGResponse)
async def query_self_correct(request: QueryRequest):
    start_time = time.time()
    try:
        # 1. INITIAL VECTOR SEARCH
        vec_docs = vectorstore.similarity_search(request.question, k=2)
        initial_context = "\n\n".join([d.page_content for d in vec_docs])

        # 2. THE GRADER AGENT (LLM-AS-A-JUDGE)
        grader_prompt = ChatPromptTemplate.from_template(
            """You are a strict grading agent for a corporate database. 
            Does the following document contain information relevant to answering the question?
            
            Question: {question}
            Document: {context}
            
            Answer ONLY with a single word: 'yes' or 'no'."""
        )
        grader_chain = grader_prompt | llm
        grade_response = grader_chain.invoke(
            {"context": initial_context, "question": request.question}
        )

        grade = grade_response.content.strip().lower()
        grade_tokens = getattr(grade_response, "usage_metadata", None) or {}

        # 3. THE DECISION ENGINE
        rewrite_tokens = {"input_tokens": 0, "output_tokens": 0}

        if "yes" in grade:
            # The context is good! Proceed normally.
            final_context = initial_context
            correction_log = (
                "⚖️ GRADER DECISION: ✅ RELEVANT. Proceeding directly to generation."
            )
            final_docs = vec_docs
        else:
            # The context is bad! Trigger Self-Correction!
            correction_log = "⚖️ GRADER DECISION: ❌ IRRELEVANT. Triggering Query Rewrite and BM25 Fallback Search..."

            # 3a. Rewrite the Query
            rewrite_prompt = ChatPromptTemplate.from_template(
                "The user asked: '{question}'. This failed to find results. Rewrite this into a cleaner, broader keyword search query. Return ONLY the new query."
            )
            rewrite_chain = rewrite_prompt | llm
            rewrite_resp = rewrite_chain.invoke({"question": request.question})
            new_query = rewrite_resp.content.strip()
            rewrite_tokens = getattr(rewrite_resp, "usage_metadata", None) or {}
            correction_log += f"\n🔄 REWRITTEN QUERY: '{new_query}'"

            # 3b. Fallback Search (BM25 Keyword Search)
            db_data = vectorstore.get()
            all_docs = [
                Document(page_content=t, metadata=m)
                for t, m in zip(db_data["documents"], db_data["metadatas"])
            ]
            bm25 = BM25Retriever.from_documents(all_docs)

            fallback_docs = bm25.invoke(new_query)[:2]
            final_context = "\n\n".join([d.page_content for d in fallback_docs])
            final_docs = fallback_docs

        # 4. FINAL SYNTHESIS (Generating the actual answer)
        synth_prompt = ChatPromptTemplate.from_template(
            "Answer the question using ONLY the provided context.\n\nContext:\n{context}\n\nQuestion: {question}"
        )
        synth_chain = synth_prompt | llm
        synth_response = synth_chain.invoke(
            {"context": final_context, "question": request.question}
        )
        answer = synth_response.content
        synth_tokens = getattr(synth_response, "usage_metadata", None) or {}

        # 5. TOKEN COST CALCULATION
        total_tokens = {
            "input_tokens": grade_tokens.get("input_tokens", 0)
            + rewrite_tokens.get("input_tokens", 0)
            + synth_tokens.get("input_tokens", 0),
            "output_tokens": grade_tokens.get("output_tokens", 0)
            + rewrite_tokens.get("output_tokens", 0)
            + synth_tokens.get("output_tokens", 0),
        }

        latency = round(time.time() - start_time, 2)
        return RAGResponse(
            pipeline="Self-Correcting RAG (CRAG)",
            answer=answer,
            retrieved_chunks=[d.page_content for d in final_docs],
            correction_log=correction_log,
            latency=latency,
            tokens=total_tokens,
        )
    except Exception as e:
        print(f"\n❌ PIPELINE D CRASHED: {repr(e)}\n")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
