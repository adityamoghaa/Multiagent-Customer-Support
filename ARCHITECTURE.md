# Architecture — Multi-Agent Customer Support (LLMOps Week 7)

## Request Flow

```
Client (curl / browser)
    │
    ▼
┌──────────────────────────────────┐
│  FastAPI  (app/main.py)          │
│  POST /chat                      │
│                                  │
│  1. Rate Limiter ────────────┐   │
│     (in-memory per-customer) │   │  → 429 if exceeded
│                              ▼   │
│  2. Input Guardrails ────────┐   │
│     (tool_agent.py patterns  │   │  → 400 if blocked
│      + content filter)       ▼   │
│                                  │
│  3. Classifier ──────────────┐   │
│     (keyword-based routing)  │   │
│                              ▼   │
│  4. Agent Pipeline               │
│     ├─ BillingAgent              │
│     ├─ TechnicalSupportAgent     │
│     ├─ ProductInfoAgent          │
│     └─ EscalationManager         │
│                              │   │
│  5. Sentiment Analysis *     │   │  * disabled by default
│                              ▼   │
│  6. PII Redaction ───────────┐   │
│     (regex: email, phone,    │   │
│      CC, SSN)                ▼   │
│                                  │
│  7. SQLite Logging               │
│     (logs.db: query, answer,     │
│      latency, tokens, cost)      │
│                              │   │
│  8. SSE Streaming Response   │   │
│     (word-by-word chunks)    ▼   │
│                                  │
└──────────────────────────────────┘
    │
    ▼
Client receives:
  event: metadata  { thread_id, category, agent, sentiment, latency }
  data: word1
  data: word2 ...
  event: done
```

## Module Map

| Module | Purpose | Modified? |
|--------|---------|-----------|
| `multiagent_support/classifier.py` | Keyword-based ticket classification | No |
| `multiagent_support/agents.py` | 4 rule-based specialist agents | No |
| `multiagent_support/sentiment.py` | DistilBERT sentiment analysis | No |
| `multiagent_support/proactive.py` | GPT-2 suggestion generation | No |
| `multiagent_support/tool_agent.py` | Pydantic schemas, guardrails, tools | No |
| `multiagent_support/models.py` | SQLAlchemy ticket model | No |
| `app/main.py` | FastAPI service, SSE streaming | **New** |
| `app/guardrails.py` | PII redaction, rate limiting, content filter | **New** |
| `app/logging_middleware.py` | SQLite request logging, metrics | **New** |
| `app/dashboard.py` | Server-rendered HTML dashboard | **New** |

## Key Design Decisions

### Simulated Streaming (Not Real Token Streaming)

The agents in `multiagent_support/agents.py` return complete strings synchronously.
There is no LLM API call with token-by-token generation happening underneath.

The `/chat` endpoint **simulates** SSE streaming for UX purposes by splitting the
complete agent response into words and sending them with a configurable delay
(`STREAM_DELAY_MS`, default 50ms). This is explicitly a **UX simulation**, not true
token-level generation streaming. A real production system would replace this with
an actual LLM API call that supports streaming (e.g., OpenAI's streaming, LangChain
streaming callbacks, or LangGraph's astream).

### Resolution Rate Metric

The dashboard displays "Resolution Rate (non-escalated)" — the percentage of
requests that were handled directly by a specialist agent without being routed
to the Escalation Manager. This is a **proxy metric**, not a direct measure of
response quality or customer satisfaction.

### HuggingFace Model Toggle

Sentiment analysis (DistilBERT), proactive suggestions (GPT-2), and translation
(Helsinki-NLP) are disabled by default (`ENABLE_HF_MODELS=false`) because:
- They download 500MB+ of model weights on first use
- They add significant startup latency
- The core classify → agent → respond pipeline works without them

Set `ENABLE_HF_MODELS=true` to enable them when running locally with models cached.

---

## What's NOT Production-Grade

This section is an **honest scope note** about limitations, not a TODO list that
blocks deployment for a learning exercise.

| Component | Current State | Production Alternative |
|-----------|--------------|----------------------|
| **Rate Limiter** | In-memory `dict` — resets on restart, single-process only | Redis-backed sliding window (e.g., `slowapi` + Redis) |
| **PII Redaction** | Regex patterns — misses context-dependent PII, false positives on numbers | ML-based NER (Presidio, Google DLP API) |
| **Metrics Store** | SQLite file — single-writer, no concurrent writes, local only | Prometheus + Grafana, or a time-series database |
| **Authentication** | None — no auth on any endpoint | OAuth2 / API keys / JWT |
| **TLS** | None — HTTP only | Reverse proxy (nginx) with TLS termination |
| **Streaming** | Simulated word-by-word chunking | Real LLM API streaming (OpenAI, Gemini, etc.) |
| **Observability** | SQLite logs + in-app dashboard | OpenTelemetry → Jaeger/Datadog/GCP Cloud Trace |
| **Agent Intelligence** | Keyword matching, rule-based responses | LLM-powered agents (LangGraph, CrewAI, etc.) |
| **Distributed Tracing** | None | OpenTelemetry spans across services |
| **Secret Management** | Environment variables | GCP Secret Manager / HashiCorp Vault |
| **Container Orchestration** | Docker Compose (single host) | Kubernetes / Cloud Run |
| **Database** | SQLite for both tickets and logs | PostgreSQL, with separate OLAP for analytics |
