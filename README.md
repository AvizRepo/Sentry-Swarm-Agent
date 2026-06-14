# 🛰️ Incident War-Room — an Agent Swarm

**Microsoft Build AI Hackathon · Theme: Agent Swarms · Model: `gemma-4-31b-it`**

A swarm of specialized AI agents that diagnoses a live system outage the way a
real on-call team does — they **triage, form competing hypotheses, gather
evidence, red-team each other, and converge on a root cause** — all visualized
in real time so you watch the swarm *think*.

This is deliberately **not** "one smart agent with tools." It is a visible team
of specialists solving something a single agent can't do alone: reach a
*defensible* conclusion through parallel investigation and adversarial debate.

---

## The swarm

```
            ┌─────────┐
            │ Triage  │  classifies severity, decides how many investigators to spawn
            └────┬────┘
       ┌─────────┼─────────┐
   ┌───▼──┐  ┌───▼──┐  ┌───▼──┐
   │Hyp 1 │  │Hyp 2 │  │Hyp 3 │   parallel — each takes a DISTINCT angle
   └───┬──┘  └───┬──┘  └───┬──┘
   ┌───▼──┐  ┌───▼──┐  ┌───▼──┐
   │Ev 1  │  │Ev 2  │  │Ev 3  │   parallel — pull supporting/contradicting evidence
   └───┬──┘  └───┬──┘  └───┬──┘
       └─────────┼─────────┘
              ┌──▼───┐
              │Critic│   red-teams every hypothesis
              └──┬───┘
              ┌──▼───┐
              │Judge │   weighs evidence + attacks, converges on root cause + fix
              └──────┘
```

| Agent | Role |
|-------|------|
| **Triage** | Frames the incident, sets severity, decides swarm size + investigation angles |
| **Hypothesis ×N** | Each independently proposes a root cause from a distinct angle (parallel) |
| **Evidence ×N** | Finds concrete supporting/contradicting log lines & metrics (parallel) |
| **Critic** | Adversarially attacks every hypothesis to expose weak reasoning |
| **Judge** | Converges on the single best-supported root cause + remediation plan |

---

## Architecture notes (why it's built this way)

- **Model access:** Google Generative Language API (`generateContent`) for
  `gemma-4-31b-it` — *not* OpenAI-compatible. `backend/gemma_client.py` speaks
  that format directly and parses JSON out of the model's "think out loud" output
  (with a strict self-repair retry on parse failure).
- **No heavy framework.** The orchestrator is ~150 lines of `asyncio`. Agents run
  in true parallel via `asyncio.gather`, and the swarm topology is explicit and
  auditable rather than hidden inside a framework. (LangGraph's Google connector
  targets Gemini, not Gemma — wrapping it was unnecessary risk.)
- **Live streaming:** every agent state change is emitted as an event over a
  **WebSocket** and rendered as a glowing node graph in the browser.

## Stack

Python · FastAPI · asyncio · httpx · WebSocket · vanilla-JS SVG graph · Docker

---

## Run it

### Local
```bash
pip install -r requirements.txt
cd backend
uvicorn main:app --reload
# open http://localhost:8000  →  Click "🔑 Key" to configure your API keys  →  click "Run Swarm"
```

### Docker
```bash
docker compose up --build
# open http://localhost:8000  →  Click "🔑 Key" to configure your API keys
```

### Headless (console)
```bash
cd backend && python orchestrator.py
```

---

## The demo incident

`data/incident.json` — *INC-4821: Checkout latency spike & elevated 5xx*. A deploy
quietly cut the DB connection-pool max from 50→10 while adding a synchronous
fraud-check that holds transactions open → **connection pool exhaustion**. Redis
eviction and the payment gateway are planted **red herrings** so the Critic and
Judge have something real to argue about. Swap in your own incident JSON to
diagnose anything.
