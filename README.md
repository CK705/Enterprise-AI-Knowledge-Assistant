# Enterprise AI Knowledge Assistant (RAG)

This M.Tech research project at IIT Patna compares four retrieval-augmented generation pipelines for enterprise document question answering. The current demo includes a React dashboard, a FastAPI API, document uploads, and a shared persistent Chroma index.

## Implemented pipelines

| Pipeline | API endpoint | Retrieval and generation |
| --- | --- | --- |
| A · Naive | `POST /query/naive` | Dense retrieval followed by answer generation. |
| B · Hybrid | `POST /query/hybrid` | Dense retrieval and per-request BM25 search, with results deduplicated before generation. |
| C · Multi-Hop | `POST /query/multihop` | Plans two search queries upfront, retrieves evidence for both, then synthesizes an answer. |
| D · CRAG | `POST /query/self_correct` | Grades the retrieved evidence once, then generates an answer or abstains. |

The current chat model is Groq's `openai/gpt-oss-120b`. Google AI Studio supplies `models/gemini-embedding-001` for document and query embeddings. Each provider can use up to three credentials for same-model failover on rate limits and transient errors. Credentials that share an upstream quota may reach the same limit.

## Run locally on Windows

Use Python 3.12 and a Node.js installation with npm. Run these commands in PowerShell:

```powershell
git clone --branch phase-2 https://github.com/CK705/Enterprise-AI-Knowledge-Assistant.git
cd Enterprise-AI-Knowledge-Assistant
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd --prefix rag-frontend ci
```

Create `.env` in the repository root with your own provider keys. The numbered keys are optional.

```dotenv
GROQ_API_KEY=your_groq_key
GOOGLE_API_KEY=your_google_ai_studio_key
# GROQ_API_KEY_2=
# GROQ_API_KEY_3=
# GOOGLE_API_KEY_2=
# GOOGLE_API_KEY_3=
```

Start FastAPI from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001
```

In a second terminal, start the frontend:

```powershell
npm.cmd --prefix rag-frontend run dev
```

Open `http://localhost:5173`. The frontend defaults to `http://localhost:8001` for API calls. Set `VITE_API_BASE_URL` in `rag-frontend/.env` if you use a different API address.

Sign in locally with the demo account `emp_charlie` and password `password123`. Upload PDFs or DOCX files to make them searchable across all four pipelines. Original files are stored in `raw_documents/`, and chunks and embeddings persist in the `langchain` Chroma collection under `enterprise_rag_db/`. Startup can backfill supported documents that are missing from the index. Assistant answers support Markdown tables.

**Local demo scope.** The application uses demo accounts and JWT authentication. Document-level role filtering is currently disabled during retrieval. Use sample documents for this setup. The adaptive pipeline, verified FAQ, and multimodal routing are planned.

## Evaluation

The historical Phase 1 artifacts in [data_and_results/](data_and_results/) contain 68 saved cases from an earlier model and code configuration without retrieval RBAC. The current dataset contains 100 rows. Use question text and reference answers when reconciling historical cases, since some IDs changed. The historical RAGAS results do not measure the current configuration.

The current direct-provider configuration completed a live functional smoke test with **20 successful requests across five questions and four pipelines**. The run measured successful responses and latency. Answer correctness and live backup-key activation were outside its scope.

To repeat the functional smoke test with FastAPI running:

```powershell
.\.venv\Scripts\python.exe batch_evaluate.py --ids 1 2 3 4 5 --username emp_charlie --output benchmark_smoke.csv
```

The runner prompts for the demo password and writes to a new CSV. Run RAGAS separately on saved answers and retrieved contexts. The [evaluation notebook](ragas-evaluation.ipynb) records the historical grading workflow. Review benchmark exports before sharing them because they can contain document excerpts.
