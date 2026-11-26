import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './App.css';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001';

const answerComponents = {
  table: ({ node, ...props }) => (
    <div className="answer-table-scroll" tabIndex={0} role="region" aria-label="Answer table">
      <table {...props} />
    </div>
  ),
};

function Answer({ result, loading, loadingText }) {
  if (!result) {
    return <p>{loading ? loadingText : 'Awaiting execution...'}</p>;
  }

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={answerComponents}>
      {result.answer}
    </ReactMarkdown>
  );
}

const formatApiError = (payload) => {
  if (!payload) return 'Upload failed.';

  if (typeof payload === 'string') return payload;

  if (typeof payload === 'object') {
    if (payload.detail) return formatApiError(payload.detail);
    if (payload.message) return payload.message;
    if (payload.error) return payload.error;
    return JSON.stringify(payload);
  }

  return String(payload);
};

function App() {
  // --- PHASE 2: AUTHENTICATION STATE ---
  const [token, setToken] = useState(localStorage.getItem("token") || null);
  const [userRole, setUserRole] = useState(localStorage.getItem("role") || null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");

  // --- PHASE 2: INGESTION STATE ---
  const [file, setFile] = useState(null);
  const [uploadStatus, setUploadStatus] = useState("");

  // --- PIPELINE STATES ---
  const [question, setQuestion] = useState("");
  const [loadingA, setLoadingA] = useState(false);
  const [loadingB, setLoadingB] = useState(false);
  const [loadingC, setLoadingC] = useState(false);
  const [loadingD, setLoadingD] = useState(false);
  
  const [naiveResult, setNaiveResult] = useState(null);
  const [hybridResult, setHybridResult] = useState(null);
  const [multiHopResult, setMultiHopResult] = useState(null);
  const [selfCorrectResult, setSelfCorrectResult] = useState(null);

  // --- AUTHENTICATION LOGIC ---
  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_BASE_URL}/api/documents/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      
      if (res.ok) {
        const data = await res.json();
        setToken(data.access_token);
        setUserRole(data.role);
        localStorage.setItem("token", data.access_token);
        localStorage.setItem("role", data.role);
        setAuthError("");
      } else {
        setAuthError("❌ Invalid corporate credentials");
      }
    } catch (err) {
      setAuthError("⚠️ Backend offline. Please start FastAPI.");
    }
  };

  const handleLogout = () => {
    setToken(null);
    setUserRole(null);
    localStorage.removeItem("token");
    localStorage.removeItem("role");
  };

  // --- INGESTION LOGIC ---
  const handleFileUpload = async (e) => {
    e.preventDefault();
    if (!file) {
      setUploadStatus("❌ Please choose a PDF or DOCX file first.");
      return;
    }
    if (!token) {
      setUploadStatus("❌ Please log in before uploading a document.");
      return;
    }

    setUploadStatus("Uploading & Vectorizing...");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE_URL}/api/documents/upload`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData
      });

      const responseText = await res.text();
      if (res.ok) {
        setUploadStatus("✅ Document uploaded and indexed successfully.");
        setFile(null);
      } else {
        let detail = 'Upload failed.';
        try {
          const payload = JSON.parse(responseText);
          detail = formatApiError(payload);
        } catch {
          detail = responseText || detail;
        }
        setUploadStatus(`❌ ${detail}`);
      }
    } catch (error) {
      setUploadStatus("⚠️ Server Error during ingestion. Check the backend is running.");
    }
  };

  // --- SECURE QUERY LOGIC (PHASE 1 WRAPPERS) ---
  const fetchSecurePipeline = async (endpoint, setter, loader) => {
    if (!question.trim()) return;
    loader(true);
    setter(null);
    try {
      const data = await fetch(`${API_BASE_URL}/${endpoint}`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}` // Injecting the JWT Token
        },
        body: JSON.stringify({ question: question })
      }).then(res => res.json());
      setter(data);
    } catch (error) {
      console.error(error);
    } finally {
      loader(false);
    }
  };

  // --- LOGIN SCREEN RENDER ---
  if (!token) {
    return (
      <div className="login-wrapper">
        <div className="login-card">
          <h2>🏢 Enterprise Knowledge SSO</h2>
          <p>Phase II Secure Authentication Gateway</p>
          <form onSubmit={handleLogin} className="login-form">
            <input type="text" placeholder="Username (e.g., admin_alice)" value={username} onChange={e => setUsername(e.target.value)} required />
            <input type="password" placeholder="Password (password123)" value={password} onChange={e => setPassword(e.target.value)} required />
            <button type="submit" className="login-btn">Authenticate</button>
            {authError && <p className="error-text">{authError}</p>}
          </form>
        </div>
      </div>
    );
  }

  // --- MAIN DASHBOARD RENDER ---
  return (
    <div className="assistant-container">
      <header className="app-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1>🤖 Enterprise Knowledge Assistant</h1>
          <p>Omni-Modal Architecture — Secure Environment</p>
        </div>
        <div className="auth-badge">
          <span className={`role-pill role-${userRole?.toLowerCase()}`}>Badge: {userRole}</span>
          <button onClick={handleLogout} className="logout-btn">Logout</button>
        </div>
      </header>

      <section className="control-panel" style={{ display: 'flex', gap: '20px', marginBottom: '30px', flexWrap: 'wrap' }}>
        
        {/* QUERY INTERFACE (Available to all users) */}
        <div className="search-box-panel" style={{ flex: '2', minWidth: '400px' }}>
          <h3>Knowledge Retrieval</h3>
          <div className="search-bar" style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
            <input 
              type="text" 
              placeholder="Ask anything requiring connected cross-document corporate data..."
              value={question} 
              onChange={(e) => setQuestion(e.target.value)}
              disabled={loadingA || loadingB || loadingC || loadingD}
            />
            <div className="execution-controls" style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
              <button onClick={() => fetchSecurePipeline('query/naive', setNaiveResult, setLoadingA)} disabled={loadingA} className="submit-btn">
                {loadingA ? "🤔..." : "Naive"}
              </button>
              <button onClick={() => fetchSecurePipeline('query/hybrid', setHybridResult, setLoadingB)} disabled={loadingB} className="submit-btn">
                {loadingB ? "🤔..." : "Hybrid"}
              </button>
              <button onClick={() => fetchSecurePipeline('query/multihop', setMultiHopResult, setLoadingC)} disabled={loadingC} className="submit-btn" style={{ backgroundColor: '#10b981' }}>
                {loadingC ? "🤔..." : "Multi-Hop"}
              </button>
              <button onClick={() => fetchSecurePipeline('query/self_correct', setSelfCorrectResult, setLoadingD)} disabled={loadingD} className="submit-btn" style={{ backgroundColor: '#f59e0b' }}>
                {loadingD ? "⚖️..." : "CRAG"}
              </button>
            </div>
          </div>
        </div>

        {/* DATA INGESTION PANEL (available to all authenticated users) */}
        <div className="admin-ingest-panel" style={{ flex: '1', minWidth: '300px', background: '#f8fafc', padding: '20px', borderRadius: '12px', border: '1px solid #e2e8f0' }}>
          <h3 style={{ marginTop: 0, color: '#0f172a' }}>📥 Data Ingestion</h3>
          <form onSubmit={handleFileUpload} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <input type="file" accept=".pdf,.docx" onChange={(e) => setFile(e.target.files[0])} required />
            
            <button type="submit" className="submit-btn" style={{ backgroundColor: '#3b82f6', width: '100%' }}>
              Upload & Ingest Vector
            </button>
            {uploadStatus && <p style={{ fontSize: '0.85rem', margin: 0, color: uploadStatus.includes('✅') ? 'green' : 'red' }}>{uploadStatus}</p>}
          </form>
        </div>
      </section>

      {/* --- DASHBOARD GRID (Remains largely the same) --- */}
      <section className="dashboard-grid">
        {/* PANEL A DISPLAY */}
        <div className="pipeline-card style-naive">
          <h2>Pipeline A: Naive RAG</h2>
          <div className="metrics-row">
            {naiveResult?.latency && <span className="pill telemetry">⏱️ {naiveResult.latency}s</span>}
          </div>
          <div className="answer-viewport">
            <Answer result={naiveResult} loading={loadingA} loadingText="Processing Turn..." />
          </div>
        </div>

        {/* PANEL B DISPLAY */}
        <div className="pipeline-card style-hybrid">
          <h2>Pipeline B: Hybrid RAG</h2>
          <div className="metrics-row">
            {hybridResult?.latency && <span className="pill telemetry">⏱️ {hybridResult.latency}s</span>}
          </div>
          <div className="answer-viewport">
            <Answer result={hybridResult} loading={loadingB} loadingText="Processing Turn..." />
          </div>
        </div>

        {/* PANEL C DISPLAY */}
        <div className="pipeline-card style-multihop">
          <h2>Pipeline C: Agentic Multi-Hop</h2>
          <div className="metrics-row">
            {multiHopResult?.latency && <span className="pill telemetry optimal">⏱️ {multiHopResult.latency}s</span>}
          </div>
          <div className="answer-viewport">
            <Answer result={multiHopResult} loading={loadingC} loadingText="Decomposing queries & linking hops..." />
          </div>
        </div>

        {/* PANEL D DISPLAY */}
        <div className="pipeline-card style-selfcorrect">
          <h2>Pipeline D: CRAG</h2>
          <div className="metrics-row">
            {selfCorrectResult?.latency && <span className="pill telemetry judge">⏱️ {selfCorrectResult.latency}s</span>}
          </div>
          <div className="answer-viewport">
            <Answer result={selfCorrectResult} loading={loadingD} loadingText="Grading retrieved context..." />
          </div>
        </div>
      </section>
    </div>
  );
}

export default App;
