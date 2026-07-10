# 🤖 Autonomous Document Agent

A Python-based AI agent that turns a plain English business request into a fully formatted Microsoft Word document — automatically. No templates, no manual writing, no configuration. Just describe what you need and the agent figures out the rest.

---

## What It Does

You type something like:

> *"Create a project proposal for migrating our data warehouse to AWS Redshift."*

And within a couple of minutes, you get a professionally structured Word document with:

- A title page
- A table of contents
- 5–7 well-written sections with formal business prose
- An agent reflection appendix showing quality scores per section

The agent decides the document type, plans the structure, writes every section, reviews its own output, rewrites anything that doesn't meet quality standards, and hands you the final `.docx` — all on its own.

---

## How It Works

The agent runs a four-step pipeline on every request:

```
Your Request
     │
     ▼
  plan()       Decides document type, generates task list, designs section outline
     │
     ▼
  execute()    Writes content for each section in parallel
     │
     ▼
  reflect()    Scores each section 1–10, rewrites anything below 7
     │
     ▼
  render()     Builds the .docx with title page, TOC, sections, and reflection appendix
     │
     ▼
  Download
```

Each step is a separate, focused LLM call. This keeps prompts tight, reduces hallucination, and produces more coherent output than asking the model to do everything at once.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API & Web UI | FastAPI |
| LLM (local) | Ollama + llama3 |
| LLM (cloud/free) | Groq API (llama3-8b-8192) |
| Document generation | python-docx |
| HTTP client | httpx |
| Input validation | Pydantic v2 |
| Parallelism | ThreadPoolExecutor |

---

## Project Structure

```
TODO_agent/
├── main.py          # FastAPI app, routes, built-in HTML UI
├── agent.py         # DocumentAgent — plan, execute, reflect, render
├── llm_utils.py     # LLM HTTP calls, JSON extraction, retry logic
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env             # Your API keys (never commit this)
└── .gitignore
```

---

## Getting Started

**1. Install Ollama and pull the model**

```bash
# Download from https://ollama.com and then:
ollama pull llama3
```

**2. Clone the repo and install dependencies**

```bash
git clone https://github.com/yourname/TODO_agent.git
cd TODO_agent
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

**3. Start the server**

```bash
uvicorn main:app --reload --port 8000
```

**4. Open your browser**

```
http://127.0.0.1:8000
```

That's it. Type your request and hit Generate.

---

## Using the Web UI

The UI lives at `http://127.0.0.1:8000`. No separate frontend to install.

1. Type your business request in the text area
2. Press **Generate Document** (or `Ctrl+Enter`)
3. Watch the four pipeline steps complete in real time
4. See the document type, task list, section previews, and reflection summary
5. Click **Download .docx** to save the file

---

## API Reference

If you want to call the agent programmatically:

**Generate a document**

```http
POST /agent
Content-Type: application/json

{
  "request": "Write a market entry plan for launching a SaaS product in Europe."
}
```

Response:

```json
{
  "job_id": "09f53917-7696-4424-beb9-512a47f47e72",
  "request": "Write a market entry plan...",
  "document_type": "plan",
  "tasks": ["Research target markets", "Analyse competitors", "..."],
  "sections": [
    { "title": "Executive Summary", "summary": "This plan outlines..." },
    "..."
  ],
  "reflection": "All sections passed quality review without rewrites.",
  "download_url": "/download/09f53917-7696-4424-beb9-512a47f47e72"
}
```

**Download the document**

```http
GET /download/{job_id}
```

Returns the `.docx` file as a binary stream.

**Health check**

```http
GET /health
```

---

## Example Requests

**Standard request**
> Create a project proposal for migrating our on-premise data warehouse to AWS Redshift.

The agent produces a `proposal` with sections like Executive Summary, Current State Assessment, Migration Benefits, Technical Requirements, Risk Management, and Implementation Timeline.

**Ambiguous request**
> We need a document about expanding our business into new markets.

The agent infers this is an `analysis`, makes reasonable assumptions about scope, and produces sections covering Market Opportunity, Competitive Landscape, Entry Strategy, Financial Projections, and Risk Assessment — all from four vague words.

---

## Engineering Highlights

**Multi-step planning** — The agent separates planning from writing. It first produces a validated JSON schema (document type, tasks, sections) before generating a single word of content. This means the structure is always coherent before writing begins.

**Reflection and self-correction** — After writing, the agent reviews every section independently, scores it from 1 to 10, and rewrites any section scoring below 7. The final document includes a quality report showing what was changed and why.

**Parallel execution** — Section content generation and reflection reviews run in parallel using a thread pool, cutting total time significantly compared to sequential calls.

**Robust JSON handling** — LLMs sometimes wrap JSON in markdown fences or add conversational prose. The `_extract_json` function handles this with a three-layer fallback: direct parse, bracket scanning, and markdown stripping. Failed attempts retry with a stricter prompt.

**No stray formatting** — Every body text run in the document has `bold=False` and `italic=False` set explicitly. A `_clean_paragraphs` method strips any markdown artifacts (`**bold**`, `*italic*`, `# headings`) that slip through the LLM before they reach the document renderer.

---


## Known Limitations

- Documents are stored in memory and lost on server restart. For production, use S3 or a database.
- On CPU, each request takes 2–4 minutes with Ollama. Use Groq or a GPU-backed instance for faster results.
- The agent makes its own assumptions for vague requests. For highly specific documents, a more detailed request produces better output.

---

## License

MIT
