"""
FastAPI server: serves the UI and streams a live swarm run over WebSocket.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import orchestrator

# Minimum structure an uploaded incident must have to run.
REQUIRED_KEYS = ("title", "summary", "alerts", "metrics", "deploys", "logs")


def valid_incident(d: object) -> bool:
    if not isinstance(d, dict):
        return False
    if not all(k in d for k in REQUIRED_KEYS):
        return False
    return any(d.get(k) for k in ("alerts", "metrics", "logs"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-20s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("swarm.server")

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# Bundled sample incidents the user can pick from (first is the default).
PRESETS = {
    "checkout": "incident.json",
    "worker": "incident_worker.json",
    "auth": "incident_auth.json",
}


def load_preset(key: str) -> dict:
    with open(os.path.join(DATA_DIR, PRESETS[key]), "r", encoding="utf-8") as f:
        return json.load(f)


app = FastAPI(title="SentrySwarm AI")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


@app.get("/api/incidents")
async def list_incidents() -> list[dict]:
    out = []
    for key in PRESETS:
        inc = load_preset(key)
        out.append({"key": key, "id": inc.get("id"), "title": inc.get("title"),
                    "summary": inc.get("summary", "")})
    return out


@app.get("/api/incident")
async def get_incident(key: str = "checkout") -> dict:
    if key not in PRESETS:
        key = "checkout"
    return load_preset(key)


@app.websocket("/ws/run")
async def run(ws: WebSocket) -> None:
    await ws.accept()
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(ev: dict) -> None:
        await queue.put(ev)

    # The client sends the incident to diagnose as its first message.
    # Empty / invalid payloads fall back to the bundled sample.
    incident = orchestrator.load_incident()
    selected_model = ""
    user_api_key = ""
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=10.0)
        sent = json.loads(raw) if raw.strip() else {}
        if isinstance(sent, dict) and "incident" in sent:
            inc = sent.get("incident")
            if valid_incident(inc):
                incident = inc
            selected_model = sent.get("model", "")
            user_api_key = sent.get("apiKey", "")
            log.info("using dynamic model config: model=%s", selected_model)
        elif valid_incident(sent):
            incident = sent
            log.info("using uploaded incident: %s", sent.get("id", "(no id)"))
    except (asyncio.TimeoutError, json.JSONDecodeError, WebSocketDisconnect):
        pass
    log.info("client connected, running incident %s", incident.get("id"))

    import gemma_client
    import agents
    import httpx

    async def handle_retry(agent_id: str, context: dict) -> None:
        log.info("retrying agent query: %s", agent_id)
        gemma_client.current_model.set(selected_model)
        gemma_client.current_api_key.set(user_api_key)
        
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=15.0)) as client:
            try:
                role = agent_id.split("-")[0]
                if agent_id == "triage":
                    role = "triage"
                elif agent_id == "critic":
                    role = "critic"
                elif agent_id == "judge":
                    role = "judge"
                
                await emit({"type": "agent", "id": agent_id, "role": role, "label": agent_id.capitalize(), "status": "thinking"})
                
                async def tok(delta: str):
                    await emit({"type": "token", "id": agent_id, "delta": delta})
                
                inc_text = agents.format_incident(incident)
                
                if agent_id == "triage":
                    res = await agents.triage(inc_text, client, on_token=tok)
                    await emit({"type": "agent", "id": agent_id, "role": role, "label": "Triage", "status": "done", "detail": f"{res.get('severity', '?')} · {res.get('one_line', '')}", "data": res})
                elif agent_id.startswith("hyp-"):
                    idx = int(agent_id.split("-")[1])
                    angle = context.get("angle", "")
                    res = await agents.hypothesize(inc_text, angle, idx, client, on_token=tok)
                    res["id"] = idx
                    await emit({"type": "agent", "id": agent_id, "role": "hypothesis", "label": f"Hypothesis {idx}", "status": "done", "detail": res.get("hypothesis", ""), "data": res})
                elif agent_id.startswith("ev-"):
                    idx = int(agent_id.split("-")[1])
                    hyp = context.get("hypothesis", {})
                    res = await agents.gather_evidence(inc_text, hyp, client, on_token=tok)
                    res["id"] = idx
                    await emit({"type": "agent", "id": agent_id, "role": "evidence", "label": f"Evidence {idx}", "status": "done", "detail": f"strength {res.get('evidence_strength', 0)}", "data": res})
                elif agent_id == "critic":
                    bundle = context.get("bundle", [])
                    res = await agents.critique(inc_text, bundle, client, on_token=tok)
                    await emit({"type": "agent", "id": agent_id, "role": role, "label": "Critic", "status": "done", "detail": "attacked all hypotheses", "data": res})
                elif agent_id == "judge":
                    bundle = context.get("bundle", [])
                    crit = context.get("critiques", {})
                    res = await agents.judge(inc_text, bundle, crit, client, on_token=tok)
                    
                    hypotheses = [b for b in bundle]
                    plaus = {c.get("id"): c.get("plausibility")
                             for c in (crit.get("critiques") or []) if isinstance(c, dict)}
                    win_id = res.get("winning_hypothesis_id")
                    ranks = []
                    for h in hypotheses:
                        hid = h["id"]
                        score = plaus.get(hid)
                        if score is None:
                            score = h.get("evidence", {}).get("evidence_strength")
                        if score is None:
                            score = h.get("confidence", 0)
                        ranks.append({"id": hid, "text": h.get("hypothesis", ""),
                                      "score": int(score or 0), "win": hid == win_id})
                    ranks.sort(key=lambda r: (not r["win"], -r["score"]))
                    res["_ranks"] = ranks
                    
                    await emit({"type": "agent", "id": agent_id, "role": role, "label": "Judge", "status": "done", "detail": res.get("root_cause", ""), "data": res})
                    await emit({"type": "result", "data": res})
            except Exception as e:
                await emit({"type": "error", "detail": f"Retry failed: {str(e)}"})

    async def drive() -> None:
        # Set the contextvars for this task and its children
        gemma_client.current_model.set(selected_model)
        gemma_client.current_api_key.set(user_api_key)
        try:
            await orchestrator.run_swarm(incident, emit)
        except Exception as e:  # surface swarm errors to the UI
            await queue.put({"type": "error", "detail": str(e)})
        finally:
            await queue.put({"type": "_end"})

    task = asyncio.create_task(drive())

    async def read_ws():
        nonlocal selected_model, user_api_key
        try:
            while True:
                msg = await ws.receive_text()
                data = json.loads(msg) if msg.strip() else {}
                if data.get("type") == "retry":
                    selected_model = data.get("model", selected_model)
                    user_api_key = data.get("apiKey", user_api_key)
                    asyncio.create_task(handle_retry(data.get("id"), data.get("context", {})))
        except (WebSocketDisconnect, RuntimeError):
            pass

    read_task = asyncio.create_task(read_ws())

    try:
        while True:
            ev = await queue.get()
            if ev.get("type") == "_end":
                # Keep connection open for retries
                continue
            await ws.send_json(ev)
    except (WebSocketDisconnect, RuntimeError):
        # client hit Stop / navigated away — cancel the in-flight run
        log.info("client disconnected, cancelling run")
    finally:
        if not task.done():
            task.cancel()
        if not read_task.done():
            read_task.cancel()


# Serve any other static assets if added later.
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
