import React, { useState } from 'react';
import './App.css';

function App() {
  const [question, setQuestion] = useState("");
  
  // Independent loading states
  const [loadingA, setLoadingA] = useState(false);
  const [loadingB, setLoadingB] = useState(false);
  const [loadingC, setLoadingC] = useState(false);
  const [loadingD, setLoadingD] = useState(false);
  
  // Independent result states
  const [naiveResult, setNaiveResult] = useState(null);
  const [hybridResult, setHybridResult] = useState(null);
  const [multiHopResult, setMultiHopResult] = useState(null);
  const [selfCorrectResult, setSelfCorrectResult] = useState(null);

  // --- PIPELINE A TRIGGER ---
  const runNaive = async () => {
    if (!question.trim()) return;
    setLoadingA(true);
    setNaiveResult(null);
    try {
      const data = await fetch('http://localhost:8000/query/naive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question })
      }).then(res => res.json());
      setNaiveResult(data);
    } catch (error) {
      console.error(error);
    } finally {
      setLoadingA(false);
    }
  };

  // --- PIPELINE B TRIGGER ---
  const runHybrid = async () => {
    if (!question.trim()) return;
    setLoadingB(true);
    setHybridResult(null);
    try {
      const data = await fetch('http://localhost:8000/query/hybrid', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question })
      }).then(res => res.json());
      setHybridResult(data);
    } catch (error) {
      console.error(error);
    } finally {
      setLoadingB(false);
    }
  };

  // --- PIPELINE C TRIGGER ---
  const runMultiHop = async () => {
    if (!question.trim()) return;
    setLoadingC(true);
    setMultiHopResult(null);
    try {
      const data = await fetch('http://localhost:8000/query/multihop', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question })
      }).then(res => res.json());
      setMultiHopResult(data);
    } catch (error) {
      console.error(error);
    } finally {
      setLoadingC(false);
    }
  };

  // --- PIPELINE D TRIGGER (NEW) ---
  const runSelfCorrect = async () => {
    if (!question.trim()) return;
    setLoadingD(true);
    setSelfCorrectResult(null);
    try {
      const data = await fetch('http://localhost:8000/query/self_correct', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question })
      }).then(res => res.json());
      setSelfCorrectResult(data);
    } catch (error) {
      console.error(error);
    } finally {
      setLoadingD(false);
    }
  };

  return (
    <div className="assistant-container">
      <header className="app-header">
        <h1>🤖 Enterprise Knowledge Assistant</h1>
        <p>Phase I — Real-Time Multi-Pipeline Benchmarking</p>
      </header>

      <section className="search-box-panel">
        <div className="search-bar" style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
          <input 
            type="text" 
            placeholder="Ask anything requiring connected cross-document corporate data..."
            value={question} 
            onChange={(e) => setQuestion(e.target.value)}
            disabled={loadingA || loadingB || loadingC || loadingD}
          />
          
          <div className="execution-controls" style={{ display: 'flex', gap: '10px', justifyContent: 'center', flexWrap: 'wrap' }}>
            <button onClick={runNaive} disabled={loadingA} className="submit-btn">
              {loadingA ? "🤔 Running A..." : "Run Naive RAG"}
            </button>
            <button onClick={runHybrid} disabled={loadingB} className="submit-btn">
              {loadingB ? "🤔 Running B..." : "Run Hybrid RAG"}
            </button>
            <button onClick={runMultiHop} disabled={loadingC} className="submit-btn" style={{ backgroundColor: '#10b981' }}>
              {loadingC ? "🤔 Running C..." : "Run Multi-Hop"}
            </button>
            <button onClick={runSelfCorrect} disabled={loadingD} className="submit-btn" style={{ backgroundColor: '#f59e0b' }}>
              {loadingD ? "⚖️ Grading & Running D..." : "Run Self-Correcting (CRAG)"}
            </button>
          </div>
        </div>
      </section>

      <section className="dashboard-grid">
        
        {/* PANEL A DISPLAY */}
        <div className="pipeline-card style-naive">
          <h2>Pipeline A: Naive RAG</h2>
          <div className="metrics-row">
            <span className="pill">Vector Search</span>
            {naiveResult?.latency && <span className="pill telemetry">⏱️ {naiveResult.latency}s</span>}
            {naiveResult?.tokens && (
              <span className="pill telemetry token-pill">🪙 In: {naiveResult.tokens.input_tokens || 0} | Out: {naiveResult.tokens.output_tokens || 0}</span>
            )}
          </div>
          <div className="answer-viewport">
            <h4>🎯 Response:</h4>
            <p>{naiveResult ? naiveResult.answer : (loadingA && !naiveResult ? "Processing Turn..." : "Awaiting execution...")}</p>
          </div>
        </div>

        {/* PANEL B DISPLAY */}
        <div className="pipeline-card style-hybrid">
          <h2>Pipeline B: Hybrid RAG</h2>
          <div className="metrics-row">
            <span className="pill">Vector + BM25</span>
            {hybridResult?.latency && <span className="pill telemetry">⏱️ {hybridResult.latency}s</span>}
            {hybridResult?.tokens && (
              <span className="pill telemetry token-pill">🪙 In: {hybridResult.tokens.input_tokens || 0} | Out: {hybridResult.tokens.output_tokens || 0}</span>
            )}
          </div>
          <div className="answer-viewport">
            <h4>🎯 Response:</h4>
            <p>{hybridResult ? hybridResult.answer : (loadingB && !hybridResult ? "Processing Turn..." : "Awaiting execution...")}</p>
          </div>
        </div>

        {/* PANEL C DISPLAY */}
        <div className="pipeline-card style-multihop">
          <h2>Pipeline C: Agentic Multi-Hop</h2>
          <div className="metrics-row">
            <span className="pill optimal">Autonomous Planner</span>
            {multiHopResult?.latency && <span className="pill telemetry optimal">⏱️ {multiHopResult.latency}s</span>}
            {multiHopResult?.tokens && (
              <span className="pill telemetry optimal token-pill">🪙 In: {multiHopResult.tokens.input_tokens || 0} | Out: {multiHopResult.tokens.output_tokens || 0}</span>
            )}
          </div>
          <div className="answer-viewport">
            <h4>🎯 Response:</h4>
            <p className="reasoned-response">{multiHopResult ? multiHopResult.answer : (loadingC && !multiHopResult ? "Decomposing queries & linking hops..." : "Awaiting execution...")}</p>
          </div>
          {multiHopResult?.plan && (
            <div className="agent-plan-box">
              <h5>🧠 Generated Search Plan:</h5>
              <ul>
                <li><strong>Hop 1:</strong> "{multiHopResult.plan.hop1}"</li>
                <li><strong>Hop 2:</strong> "{multiHopResult.plan.hop2}"</li>
              </ul>
            </div>
          )}
        </div>

        {/* PANEL D DISPLAY (NEW) */}
        <div className="pipeline-card style-selfcorrect">
          <h2>Pipeline D: CRAG</h2>
          <div className="metrics-row">
            <span className="pill judge">LLM-as-a-Judge</span>
            {selfCorrectResult?.latency && <span className="pill telemetry judge">⏱️ {selfCorrectResult.latency}s</span>}
            {selfCorrectResult?.tokens && (
              <span className="pill telemetry judge token-pill">🪙 In: {selfCorrectResult.tokens.input_tokens || 0} | Out: {selfCorrectResult.tokens.output_tokens || 0}</span>
            )}
          </div>
          <div className="answer-viewport">
            <h4>🎯 Response:</h4>
            <p>{selfCorrectResult ? selfCorrectResult.answer : (loadingD && !selfCorrectResult ? "Grading retrieved context..." : "Awaiting execution...")}</p>
          </div>
          {selfCorrectResult?.correction_log && (
            <div className="correction-log-box">
              <h5>🕵️‍♂️ Internal Grader Telemetry:</h5>
              <p>{selfCorrectResult.correction_log}</p>
            </div>
          )}
        </div>

      </section>
    </div>
  );
}

export default App;