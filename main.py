"""
main.py — FastAPI app with built-in browser UI.

Routes:
  GET  /          → self-contained HTML UI
  POST /agent     → runs pipeline, returns JSON + job_id
  GET  /download/{job_id} → streams the generated .docx
"""
from __future__ import annotations

import io
import logging
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, field_validator

from agent import DocumentAgent

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Autonomous Document Agent", version="1.0.0")
_agent = DocumentAgent(model="llama3")

# In-memory store: job_id → (filename, docx_bytes)
_jobs: dict[str, tuple[str, bytes]] = {}

TEMP_DIR = Path("generated_docs")
TEMP_DIR.mkdir(exist_ok=True)


# ------------------------------------------------------------------ #
# Models                                                              #
# ------------------------------------------------------------------ #

class AgentRequest(BaseModel):
    request: str

    @field_validator("request")
    @classmethod
    def validate_request(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Request must be at least 10 characters.")
        if len(v) > 2000:
            raise ValueError("Request must be under 2000 characters.")
        if re.fullmatch(r"[^a-zA-Z]*", v):
            raise ValueError("Request must contain meaningful text.")
        return v


class SectionSummary(BaseModel):
    title: str
    summary: str


class AgentResponse(BaseModel):
    job_id: str
    request: str
    document_type: str
    tasks: list[str]
    sections: list[SectionSummary]
    reflection: str
    download_url: str


# ------------------------------------------------------------------ #
# UI                                                                  #
# ------------------------------------------------------------------ #

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Autonomous Document Agent</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: #0f1117;
    color: #e2e8f0;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 48px 16px;
  }

  .card {
    background: #1a1d27;
    border: 1px solid #2d3148;
    border-radius: 16px;
    padding: 40px;
    width: 100%;
    max-width: 780px;
  }

  h1 {
    font-size: 1.6rem;
    font-weight: 700;
    color: #a78bfa;
    margin-bottom: 6px;
  }

  .subtitle {
    font-size: 0.9rem;
    color: #64748b;
    margin-bottom: 32px;
  }

  label {
    display: block;
    font-size: 0.85rem;
    font-weight: 600;
    color: #94a3b8;
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  textarea {
    width: 100%;
    height: 120px;
    background: #0f1117;
    border: 1px solid #2d3148;
    border-radius: 10px;
    color: #e2e8f0;
    font-size: 0.95rem;
    padding: 14px 16px;
    resize: vertical;
    outline: none;
    transition: border-color 0.2s;
  }

  textarea:focus { border-color: #7c3aed; }

  button#submitBtn {
    margin-top: 16px;
    width: 100%;
    padding: 14px;
    background: linear-gradient(135deg, #7c3aed, #4f46e5);
    border: none;
    border-radius: 10px;
    color: #fff;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.2s;
  }

  button#submitBtn:disabled { opacity: 0.45; cursor: not-allowed; }
  button#submitBtn:not(:disabled):hover { opacity: 0.88; }

  /* ---- Status steps ---- */
  #statusBox {
    margin-top: 28px;
    display: none;
    flex-direction: column;
    gap: 10px;
  }

  .step {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 0.9rem;
    color: #64748b;
    transition: color 0.3s;
  }

  .step.active { color: #a78bfa; }
  .step.done   { color: #34d399; }
  .step.error  { color: #f87171; }

  .step-icon {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    border: 2px solid currentColor;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.7rem;
    flex-shrink: 0;
  }

  .step.active .step-icon { animation: pulse 1s infinite; }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.4; }
  }

  /* ---- Result panel ---- */
  #resultBox {
    margin-top: 28px;
    display: none;
  }

  .result-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }

  .badge {
    background: #312e81;
    color: #a5b4fc;
    font-size: 0.75rem;
    font-weight: 700;
    padding: 4px 12px;
    border-radius: 999px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  #downloadBtn {
    background: #065f46;
    color: #6ee7b7;
    border: 1px solid #059669;
    border-radius: 8px;
    padding: 8px 18px;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    text-decoration: none;
    transition: background 0.2s;
  }

  #downloadBtn:hover { background: #047857; }

  .section-list {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-bottom: 20px;
  }

  .section-item {
    background: #0f1117;
    border: 1px solid #2d3148;
    border-radius: 8px;
    padding: 12px 16px;
  }

  .section-title {
    font-weight: 600;
    font-size: 0.9rem;
    color: #c4b5fd;
    margin-bottom: 4px;
  }

  .section-summary {
    font-size: 0.82rem;
    color: #64748b;
    line-height: 1.5;
  }

  .tasks-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 20px;
  }

  .task-chip {
    background: #1e1b4b;
    color: #a5b4fc;
    border: 1px solid #3730a3;
    border-radius: 999px;
    font-size: 0.78rem;
    padding: 4px 12px;
  }

  .reflection-box {
    background: #0f1117;
    border-left: 3px solid #7c3aed;
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
    font-size: 0.85rem;
    color: #94a3b8;
    line-height: 1.6;
  }

  .meta-label {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #475569;
    margin-bottom: 8px;
  }

  #errorBox {
    margin-top: 20px;
    display: none;
    background: #1c0a0a;
    border: 1px solid #7f1d1d;
    border-radius: 10px;
    padding: 16px;
    color: #fca5a5;
    font-size: 0.88rem;
  }
</style>
</head>
<body>

<div class="card">
  <h1>🤖 Autonomous Document Agent</h1>
  <p class="subtitle">Describe your business need — the agent plans, writes, and delivers a Word document.</p>

  <label for="requestInput">Your Request</label>
  <textarea id="requestInput" placeholder="e.g. Create a project proposal for migrating our data warehouse to AWS Redshift..."></textarea>

  <button id="submitBtn" onclick="runAgent()">Generate Document</button>

  <!-- Status steps -->
  <div id="statusBox">
    <div class="step" id="step-plan">
      <div class="step-icon">1</div> Planning document structure…
    </div>
    <div class="step" id="step-execute">
      <div class="step-icon">2</div> Writing section content…
    </div>
    <div class="step" id="step-reflect">
      <div class="step-icon">3</div> Reflecting &amp; improving quality…
    </div>
    <div class="step" id="step-render">
      <div class="step-icon">4</div> Rendering Word document…
    </div>
  </div>

  <!-- Error -->
  <div id="errorBox"></div>

  <!-- Result -->
  <div id="resultBox">
    <div class="result-header">
      <span id="docTypeBadge" class="badge"></span>
      <a id="downloadBtn" href="#" download>⬇ Download .docx</a>
    </div>

    <div class="meta-label">Tasks</div>
    <div id="tasksList" class="tasks-row"></div>

    <div class="meta-label">Sections</div>
    <ul id="sectionsList" class="section-list"></ul>

    <div class="meta-label">Agent Reflection</div>
    <div id="reflectionText" class="reflection-box"></div>
  </div>
</div>

<script>
  const STEPS = ['plan', 'execute', 'reflect', 'render'];

  function setStep(name) {
    STEPS.forEach(s => {
      const el = document.getElementById('step-' + s);
      el.className = 'step';
    });
    const idx = STEPS.indexOf(name);
    STEPS.forEach((s, i) => {
      const el = document.getElementById('step-' + s);
      if (i < idx)       el.classList.add('done');
      else if (i === idx) el.classList.add('active');
    });
  }

  function allDone() {
    STEPS.forEach(s => document.getElementById('step-' + s).className = 'step done');
  }

  async function runAgent() {
    const request = document.getElementById('requestInput').value.trim();
    if (!request) return;

    const btn = document.getElementById('submitBtn');
    btn.disabled = true;

    document.getElementById('errorBox').style.display = 'none';
    document.getElementById('resultBox').style.display = 'none';
    document.getElementById('statusBox').style.display = 'flex';
    setStep('plan');

    // Simulate step progression while waiting (real steps happen server-side)
    const stepDelay = [0, 4000, 8000, 12000];
    STEPS.forEach((s, i) => setTimeout(() => setStep(s), stepDelay[i]));

    try {
      const res = await fetch('/agent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request })
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || 'Unknown error from agent.');
      }

      allDone();
      renderResult(data);

    } catch (err) {
      STEPS.forEach(s => {
        const el = document.getElementById('step-' + s);
        if (el.classList.contains('active')) el.className = 'step error';
      });
      const eb = document.getElementById('errorBox');
      eb.textContent = '✖ ' + err.message;
      eb.style.display = 'block';
    } finally {
      btn.disabled = false;
    }
  }

  function renderResult(data) {
    document.getElementById('docTypeBadge').textContent = data.document_type;
    document.getElementById('downloadBtn').href = data.download_url;

    const tasks = document.getElementById('tasksList');
    tasks.innerHTML = data.tasks.map(t =>
      `<span class="task-chip">${t}</span>`
    ).join('');

    const sections = document.getElementById('sectionsList');
    sections.innerHTML = data.sections.map(s => `
      <li class="section-item">
        <div class="section-title">${s.title}</div>
        <div class="section-summary">${s.summary}</div>
      </li>
    `).join('');

    document.getElementById('reflectionText').textContent = data.reflection;
    document.getElementById('resultBox').style.display = 'block';
  }

  // Allow Ctrl+Enter to submit
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('requestInput').addEventListener('keydown', e => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) runAgent();
    });
  });
</script>
</body>
</html>
"""


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.get("/", response_class=HTMLResponse)
def ui():
    return HTML


@app.post("/agent", response_model=AgentResponse)
async def run_agent(body: AgentRequest) -> AgentResponse:
    try:
        state = _agent.plan(body.request)
        state = _agent.execute(state)
        state = _agent.reflect(state)
        docx_bytes = _agent.render_docx(state)
    except RuntimeError as exc:
        logger.error("Agent pipeline failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        logger.error("Agent validation error: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc))

    job_id = str(uuid.uuid4())
    filename = f"{state.document_type.replace(' ', '_')}_document.docx"
    _jobs[job_id] = (filename, docx_bytes)

    return AgentResponse(
        job_id=job_id,
        request=state.request,
        document_type=state.document_type,
        tasks=state.tasks,
        sections=[
            SectionSummary(
                title=s.title,
                summary=(s.content[:200] + "…") if len(s.content) > 200 else s.content,
            )
            for s in state.sections
        ],
        reflection=state.reflection_summary,
        download_url=f"/download/{job_id}",
    )


@app.get("/download/{job_id}")
def download(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Document not found or expired.")
    filename, docx_bytes = _jobs[job_id]
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
