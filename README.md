# Enterprise AI Knowledge Assistant (RAG)
**Phase 1: Architectural Benchmarking of RAG Systems**

This repository contains the full-stack implementation and evaluation datasets for an M.Tech research project at IIT Patna. The project benchmarks four escalating architectures of Retrieval-Augmented Generation (RAG) to mitigate parametric hallucinations in enterprise environments.

## 🏗️ Architectures Benchmarked
1. **Pipeline A (Naive RAG):** Baseline vector retrieval.
2. **Pipeline B (Hybrid RAG):** Semantic vector + Lexical BM25 search with metadata routing.
3. **Pipeline C (Agentic Multi-Hop):** Autonomous planner for multi-document synthesis.
4. **Pipeline D (Self-Correcting):** Agentic evaluation loops for strict generative safety.

## 📊 Evaluation Framework
The pipelines were rigorously benchmarked using the **RAGAS framework** against a custom-engineered synthetic dataset of 70 enterprise queries (including simple lookups, complex calculations, and unanswerable traps). 
* Evaluation Models: Llama 3.1 (8B) / Llama 3.3 (70B) via Groq
* Embeddings: Google Gemini / HuggingFace BGE

## ⚙️ Installation & Setup
1. Clone the repository:
   ```bash
   git clone [https://github.com/CK705/Enterprise_RAG.git](https://github.com/CK705/Enterprise_RAG.git)