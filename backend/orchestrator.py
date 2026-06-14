"""
The swarm orchestrator: drives Triage -> Hypothesis(parallel) -> Evidence(parallel)
-> Critic -> Judge, streaming live tokens + state events so the UI can render the
swarm thinking in real time.

`emit` is an async callback taking an event dict. Pass a console printer to run
headless, or a WebSocket sender to stream to the browser.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import Awaitable, Callable

import httpx

import agents

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

log = logging.getLogger("swarm.orchestrator")

Emit = Callable[[dict], Awaitable[None]]

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "incident.json")


def load_incident(path: str = DATA_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


async def _noop(_: dict) -> None:
    pass


async def run_swarm(incident: dict, emit: Emit | None = None) -> dict:
    emit = emit or _noop
    inc_text = agents.format_incident(incident)

    def tok(agent_id: str):
        async def _t(delta: str) -> None:
            await emit({"type": "token", "id": agent_id, "delta": delta})
        return _t

    async def agent_event(agent_id: str, role: str, label: str, status: str,
                          detail: str = "", data: dict | None = None) -> None:
        ev = {"type": "agent", "id": agent_id, "role": role, "label": label,
              "status": status}
        if detail:
            ev["detail"] = detail
        if data is not None:
            ev["data"] = data
        await emit(ev)

    log.info("=== swarm start: %s ===", incident.get("id"))

    # Generous read timeout: on big critic/judge prompts Gemma "thinks"
    # server-side for a while before the first streamed token arrives.
    timeout = httpx.Timeout(300.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        # ── Phase 1: Triage ──────────────────────────────────────────────────
        await emit({"type": "phase", "name": "triage", "label": "Triage"})
        await agent_event("triage", "triage", "Triage", "thinking")
        tri = await agents.triage(inc_text, client, on_token=tok("triage"))
        angles = tri.get("investigation_angles", [])[: tri.get("num_investigators", 3)]
        log.info("triage: %s, %d angles", tri.get("severity"), len(angles))
        await agent_event("triage", "triage", "Triage", "done",
                          f"{tri.get('severity', '?')} · {tri.get('one_line', '')}", tri)

        # ── Phase 2: Hypothesis agents in parallel ───────────────────────────
        await emit({"type": "phase", "name": "hypothesize",
                    "label": f"{len(angles)} investigators"})
        for i, angle in enumerate(angles, 1):
            await agent_event(f"hyp-{i}", "hypothesis", f"Hypothesis {i}", "spawned", angle)
            await emit({"type": "edge", "from": "triage", "to": f"hyp-{i}"})

        async def _hyp(i: int, angle: str) -> dict:
            await agent_event(f"hyp-{i}", "hypothesis", f"Hypothesis {i}", "thinking", angle)
            h = await agents.hypothesize(inc_text, angle, i, client, on_token=tok(f"hyp-{i}"))
            h["id"] = i
            await agent_event(f"hyp-{i}", "hypothesis", f"Hypothesis {i}", "done",
                              h.get("hypothesis", ""), h)
            return h

        hypotheses = await asyncio.gather(*[_hyp(i, a) for i, a in enumerate(angles, 1)])

        # ── Phase 3: Evidence agents in parallel ─────────────────────────────
        await emit({"type": "phase", "name": "evidence", "label": "Evidence"})

        async def _ev(h: dict) -> dict:
            i = h["id"]
            await agent_event(f"ev-{i}", "evidence", f"Evidence {i}", "thinking")
            await emit({"type": "edge", "from": f"hyp-{i}", "to": f"ev-{i}"})
            e = await agents.gather_evidence(inc_text, h, client, on_token=tok(f"ev-{i}"))
            e["id"] = i
            await agent_event(f"ev-{i}", "evidence", f"Evidence {i}", "done",
                              f"strength {e.get('evidence_strength', 0)}", e)
            return e

        evidence = await asyncio.gather(*[_ev(h) for h in hypotheses])
        ev_by_id = {e["id"]: e for e in evidence}
        bundle = [{**h, "evidence": ev_by_id.get(h["id"], {})} for h in hypotheses]

        # ── Phase 4: Critic ──────────────────────────────────────────────────
        await emit({"type": "phase", "name": "critic", "label": "Red-team"})
        await agent_event("critic", "critic", "Critic", "thinking")
        for i in (h["id"] for h in hypotheses):
            await emit({"type": "edge", "from": f"ev-{i}", "to": "critic"})
        crit = await agents.critique(inc_text, bundle, client, on_token=tok("critic"))
        await agent_event("critic", "critic", "Critic", "done", "attacked all hypotheses", crit)

        # ── Phase 5: Judge ───────────────────────────────────────────────────
        await emit({"type": "phase", "name": "judge", "label": "Converging"})
        await agent_event("judge", "judge", "Judge", "thinking")
        await emit({"type": "edge", "from": "critic", "to": "judge"})
        verdict = await agents.judge(inc_text, bundle, crit, client, on_token=tok("judge"))
        await agent_event("judge", "judge", "Judge", "done",
                          verdict.get("root_cause", ""), verdict)

        log.info("=== verdict: %s (%s%%) ===",
                 verdict.get("root_cause", "")[:60], verdict.get("confidence"))

        # Rank hypotheses for the end dashboard: critic plausibility, falling back
        # to evidence strength then the hypothesis's own confidence.
        plaus = {c.get("id"): c.get("plausibility")
                 for c in (crit.get("critiques") or []) if isinstance(c, dict)}
        win_id = verdict.get("winning_hypothesis_id")
        ranks = []
        for h in hypotheses:
            hid = h["id"]
            score = plaus.get(hid)
            if score is None:
                score = ev_by_id.get(hid, {}).get("evidence_strength")
            if score is None:
                score = h.get("confidence", 0)
            ranks.append({"id": hid, "text": h.get("hypothesis", ""),
                          "score": int(score or 0), "win": hid == win_id})
        ranks.sort(key=lambda r: (not r["win"], -r["score"]))
        verdict["_ranks"] = ranks

        result = {"triage": tri, "hypotheses": hypotheses, "evidence": evidence,
                  "critique": crit, "verdict": verdict}
        await emit({"type": "result", "data": verdict})
        await emit({"type": "phase", "name": "done", "label": "Resolved"})
        return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s | %(message)s",
                        datefmt="%H:%M:%S")

    async def _console(ev: dict) -> None:
        t = ev["type"]
        if t == "phase":
            print(f"\n=== {ev['label'].upper()} ===")
        elif t == "agent" and ev["status"] == "done":
            print(f"  [done] {ev['label']}: {ev.get('detail', '')}")
        elif t == "result":
            v = ev["data"]
            print("\n--- VERDICT ---")
            print(f"  Root cause: {v.get('root_cause')}")
            print(f"  Confidence: {v.get('confidence')}")
            for step in v.get("remediation", []):
                print(f"    - {step}")

    async def _main() -> None:
        await run_swarm(load_incident(), _console)

    asyncio.run(_main())
