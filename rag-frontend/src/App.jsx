import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './App.css';

const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8001';
const tokenNumber = new Intl.NumberFormat();
const pipelines = [
  { id: 'naive', name: 'Naive', description: 'Vector search', color: 'blue' },
  { id: 'hybrid', name: 'Hybrid', description: 'Vector + keyword search', color: 'violet' },
  { id: 'multihop', name: 'Multi-Hop', description: 'Two search queries', color: 'teal' },
  { id: 'self_correct', name: 'CRAG', description: 'Evidence grading', color: 'amber' },
];
const markdownComponents = {
  table: ({ node, ...props }) => (
    <div className="table-scroll" tabIndex={0} role="region" aria-label="Answer table">
      <table {...props} />
    </div>
  ),
};

async function request(path, options) {
  const response = await fetch(API + path, options);
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(typeof body?.detail === 'string' ? body.detail : `Request failed (HTTP ${response.status}).`);
    error.status = response.status;
    throw error;
  }
  if (!body) throw new Error('The server returned an empty response.');
  return body;
}

function Brand() {
  return <div className="brand"><span className="brand-mark" aria-hidden="true">K</span><span>Enterprise<br />Knowledge</span></div>;
}

function ResultCard({ pipeline, entry }) {
  const { result, error, pending } = entry || {};
  return (
    <article className="result-card">
      <header className="result-header">
        <div className="pipeline-title">
          <span className={`pipeline-dot ${pipeline.color}`} aria-hidden="true" />
          <div><h3>{pipeline.name}</h3><span>{pipeline.description}</span></div>
        </div>
        {result && (
          <div className="result-metrics">
            {result.latency != null && <span className="metric">{result.latency} s</span>}
            {result.tokens?.input_tokens != null && result.tokens?.output_tokens != null ? (
              <>
                <span className="metric">Input {tokenNumber.format(result.tokens.input_tokens)}</span>
                <span className="metric">Output {tokenNumber.format(result.tokens.output_tokens)}</span>
              </>
            ) : <span className="metric">Tokens unavailable</span>}
          </div>
        )}
      </header>
      <div className="answer">
        {pending && <p className="muted" role="status">Running pipeline…</p>}
        {error && <p className="error" role="alert">{error}</p>}
        {!entry && <p className="muted">Awaiting a query.</p>}
        {result && <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{result.answer}</ReactMarkdown>}
      </div>
      {result && (
        <div className="evidence">
          {result.plan && <details><summary>Search plan</summary><dl>{Object.entries(result.plan).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl></details>}
          {result.correction_log && <details><summary>Evidence grade</summary><p>{result.correction_log}</p></details>}
          {result.retrieved_chunks?.length > 0 && <details><summary>Retrieved evidence <span>{result.retrieved_chunks.length}</span></summary><ol>{result.retrieved_chunks.map((chunk, index) => <li key={index}>{chunk}</li>)}</ol></details>}
        </div>
      )}
    </article>
  );
}

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('token'));
  const [role, setRole] = useState(() => localStorage.getItem('role'));
  const [view, setView] = useState('query');
  const [question, setQuestion] = useState('');
  const [runQuestion, setRunQuestion] = useState('');
  const [selected, setSelected] = useState('hybrid');
  const [entries, setEntries] = useState({});
  const [running, setRunning] = useState(false);
  const [authError, setAuthError] = useState('');
  const [signingIn, setSigningIn] = useState(false);
  const [file, setFile] = useState(null);
  const [upload, setUpload] = useState({});
  const authorization = { Authorization: `Bearer ${token}` };

  function logout(message = '') {
    localStorage.removeItem('token');
    localStorage.removeItem('role');
    setToken(null);
    setRole(null);
    setEntries({});
    setQuestion('');
    setRunQuestion('');
    setUpload({});
    setFile(null);
    setView('query');
    setAuthError(message);
  }

  async function login(event) {
    event.preventDefault();
    const { username, password } = Object.fromEntries(new FormData(event.currentTarget));
    setSigningIn(true);
    setAuthError('');
    try {
      const identity = await request('/api/documents/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      localStorage.setItem('token', identity.access_token);
      localStorage.setItem('role', identity.role);
      setToken(identity.access_token);
      setRole(identity.role);
    } catch (error) {
      setAuthError(error.status ? error.message : 'Could not reach the API. Check that FastAPI is running.');
    } finally {
      setSigningIn(false);
    }
  }

  async function run(all = false) {
    const submitted = question.trim();
    if (!submitted || running) return;
    const targets = all ? pipelines : pipelines.filter(({ id }) => id === selected);
    setRunQuestion(submitted);
    setRunning(true);
    setEntries(previous => submitted === runQuestion ? previous : {});
    try {
      for (const { id } of targets) {
        setEntries(previous => ({ ...previous, [id]: { pending: true } }));
        try {
          const result = await request(`/query/${id}`, {
            method: 'POST',
            headers: { ...authorization, 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: submitted }),
          });
          setEntries(previous => ({ ...previous, [id]: { result } }));
        } catch (error) {
          if (error.status === 401) {
            logout('Your session expired. Sign in again.');
            break;
          }
          setEntries(previous => ({ ...previous, [id]: { error: error.message } }));
        }
      }
    } finally {
      setRunning(false);
    }
  }

  async function uploadFile(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData();
    data.append('file', file);
    setUpload({ pending: true, message: 'Uploading and indexing…' });
    try {
      await request('/api/documents/upload', { method: 'POST', headers: authorization, body: data });
      setUpload({ message: `${file.name} is indexed and ready to query.` });
      setFile(null);
      form.reset();
    } catch (error) {
      if (error.status === 401) logout('Your session expired. Sign in again.');
      else setUpload({ error: true, message: error.message });
    }
  }

  if (!token) {
    return (
      <main className="login-page">
        <div className="login-intro"><Brand /><h1>Enterprise knowledge workspace</h1><p>Ask questions about your documents and compare the evidence behind each answer.</p></div>
        <section className="login-card" aria-labelledby="sign-in">
          <h2 id="sign-in">Sign in</h2>
          <form onSubmit={login}>
            <label>Username<input name="username" autoComplete="username" required /></label>
            <label>Password<input name="password" type="password" autoComplete="current-password" required /></label>
            {authError && <p className="error" role="alert">{authError}</p>}
            <button className="primary" disabled={signingIn}>{signingIn ? 'Signing in…' : 'Sign in'}</button>
          </form>
        </section>
      </main>
    );
  }

  return (
    <div className="workspace">
      <aside className="sidebar">
        <Brand />
        <nav aria-label="Workspace">
          <button aria-current={view === 'query' ? 'page' : undefined} onClick={() => setView('query')}><span aria-hidden="true">⌕</span> Query workspace</button>
          <button aria-current={view === 'documents' ? 'page' : undefined} onClick={() => setView('documents')}><span aria-hidden="true">▤</span> Documents</button>
        </nav>
        <div className="session"><span>{role || 'Signed in'}</span><button onClick={() => logout()} disabled={running || upload.pending}>Sign out</button></div>
      </aside>
      <main className="main-panel">
        <header className="page-header">
          <h1>{view === 'query' ? 'Query workspace' : 'Documents'}</h1>
          <p>{view === 'query' ? 'Ask a question and compare answers across four retrieval pipelines.' : 'Add PDF or DOCX files to the shared retrieval index.'}</p>
        </header>
        <div hidden={view !== 'query'}>
          <form className="composer" onSubmit={event => { event.preventDefault(); run(); }}>
            <label htmlFor="question">Question</label>
            <textarea id="question" rows={3} placeholder="What would you like to find in your documents?" value={question} onChange={event => setQuestion(event.target.value)} disabled={running} required />
            <fieldset>
              <legend>Pipeline</legend>
              <div className="pipeline-options">
                {pipelines.map(pipeline => <label key={pipeline.id}><input type="radio" name="pipeline" value={pipeline.id} checked={selected === pipeline.id} onChange={() => setSelected(pipeline.id)} disabled={running} /><span className={`pipeline-dot ${pipeline.color}`} aria-hidden="true" />{pipeline.name}</label>)}
              </div>
            </fieldset>
            <div className="actions">
              <button className="secondary" type="button" disabled={running || !question.trim()} onClick={() => run(true)}>Compare all four</button>
              <button className="primary" disabled={running || !question.trim()}>{running ? 'Running…' : 'Run pipeline'}</button>
            </div>
          </form>
          <section aria-labelledby="results-heading" className="results">
            <h2 id="results-heading">Pipeline results</h2>
            {runQuestion && <p className="run-question">{runQuestion}</p>}
            <div className="result-grid">{pipelines.map(pipeline => <ResultCard key={pipeline.id} pipeline={pipeline} entry={entries[pipeline.id]} />)}</div>
          </section>
        </div>
        <section hidden={view !== 'documents'}>
          <form className="composer upload-form" onSubmit={uploadFile}>
            <label htmlFor="document">Document file</label>
            <input id="document" type="file" accept=".pdf,.docx" onChange={event => setFile(event.target.files[0] || null)} disabled={upload.pending} required />
            <button className="primary" disabled={!file || upload.pending}>{upload.pending ? 'Indexing…' : 'Upload and index'}</button>
            {upload.message && <p className={upload.error ? 'error' : 'notice'} role={upload.error ? 'alert' : 'status'}>{upload.message}</p>}
          </form>
        </section>
      </main>
    </div>
  );
}
