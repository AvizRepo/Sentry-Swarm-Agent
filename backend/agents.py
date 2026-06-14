"""
The specialist agents of the Incident War-Room swarm.

Each agent is a prompt + a thin async call that returns parsed JSON. The model
"thinks out loud", so every prompt demands the final answer inside a ```json
fence; gemma_client._parse_json tolerates the surrounding reasoning.
"""
from __future__ import annotations

import json
from typing import Awaitable, Callable

import httpx

from gemma_client import generate_json

OnToken = Callable[[str], Awaitable[None]]

SYSTEM = (
    "You are a senior Site Reliability Engineer in a live incident war-room. "
    "You are precise, evidence-driven, and skeptical. You never invent facts that "
    "are not in the provided incident data. "
    "Always end your reply with your final answer as a single JSON object inside a "
    "```json code fence. Output JSON only inside the fence — no trailing text."
)


def format_incident(inc: dict) -> str:
    """Render the incident bundle into a compact, readable block for prompts."""
    lines = [
        f"INCIDENT {inc['id']}: {inc['title']}",
        f"Started: {inc['started_at']}",
        f"Summary: {inc['summary']}",
        "",
        "ALERTS:",
    ]
    for a in inc["alerts"]:
        lines.append(f"  [{a['ts']}] ({a['severity']}/{a['source']}) {a['text']}")
    lines.append("")
    lines.append("METRICS (before -> after):")
    for m in inc["metrics"]:
        note = f"  // {m['note']}" if m.get("note") else ""
        lines.append(f"  {m['name']}: {m['before']} -> {m['after']}{note}")
    lines.append("")
    lines.append("RECENT DEPLOYS:")
    for d in inc["deploys"]:
        lines.append(f"  [{d['ts']}] {d['service']} by {d['author']}: {d['change']}")
    lines.append("")
    lines.append("LOG SAMPLE:")
    for l in inc["logs"]:
        lines.append(f"  [{l['ts']}] {l['service']} {l['level']}: {l['msg']}")
    return "\n".join(lines)


# ── Triage ────────────────────────────────────────────────────────────────────
async def triage(
    inc_text: str, client: httpx.AsyncClient, on_token: OnToken | None = None
) -> dict:
    prompt = f"""{inc_text}

You are the TRIAGE agent. Assess this incident and decide how to deploy the swarm.
Return JSON:
{{
  "severity": "SEV1|SEV2|SEV3",
  "one_line": "<one sentence framing of the incident>",
  "num_investigators": <integer 3 or 4>,
  "investigation_angles": ["<distinct angle 1>", "<angle 2>", ...]
}}
The angles must be DISTINCT competing directions to investigate (e.g. database,
caching layer, recent deploy, external dependency). Provide exactly
num_investigators angles."""
    return await generate_json(prompt, system=SYSTEM, temperature=0.3, client=client,
                               on_token=on_token, label="triage")


# ── Hypothesis ──────────────────────────────────────────────────────────────--
async def hypothesize(
    inc_text: str, angle: str, idx: int, client: httpx.AsyncClient,
    on_token: OnToken | None = None,
) -> dict:
    prompt = f"""{inc_text}

You are HYPOTHESIS agent #{idx}, investigating specifically this angle: "{angle}".
Propose ONE concrete root-cause hypothesis from that angle. Be specific about the
mechanism. Return JSON:
{{
  "id": {idx},
  "angle": "{angle}",
  "hypothesis": "<one-sentence root cause>",
  "mechanism": "<how this produces the observed symptoms, 2-3 sentences>",
  "confidence": <integer 0-100>
}}"""
    return await generate_json(prompt, system=SYSTEM, temperature=0.7, client=client,
                               on_token=on_token, label=f"hyp-{idx}")


# ── Evidence ───────────────────────────────────────────────────────────────---
async def gather_evidence(
    inc_text: str, hypothesis: dict, client: httpx.AsyncClient,
    on_token: OnToken | None = None,
) -> dict:
    prompt = f"""{inc_text}

You are an EVIDENCE agent. Examine this hypothesis and find concrete supporting
OR contradicting evidence strictly from the incident data above.

HYPOTHESIS #{hypothesis['id']}: {hypothesis['hypothesis']}
Mechanism: {hypothesis['mechanism']}

Return JSON:
{{
  "id": {hypothesis['id']},
  "supporting": ["<exact log line / metric that supports it>", ...],
  "contradicting": ["<anything that argues against it>", ...],
  "evidence_strength": <integer 0-100>
}}"""
    return await generate_json(prompt, system=SYSTEM, temperature=0.2, client=client,
                               on_token=on_token, label=f"ev-{hypothesis['id']}")


# ── Critic ────────────────────────────────────────────────────────────────────
async def critique(
    inc_text: str, bundle: list[dict], client: httpx.AsyncClient,
    on_token: OnToken | None = None,
) -> dict:
    packed = json.dumps(bundle, indent=2)
    prompt = f"""{inc_text}

You are the CRITIC agent (red-team). Below are competing hypotheses with their
evidence. Attack each one: find weaknesses, alternative explanations, and red
herrings. Be harsh but fair.

HYPOTHESES + EVIDENCE:
{packed}

Return JSON:
{{
  "critiques": [
    {{"id": <hypothesis id>, "weaknesses": ["..."], "plausibility": <integer 0-100>}},
    ...
  ]
}}
Include one critique object per hypothesis."""
    return await generate_json(prompt, system=SYSTEM, temperature=0.4,
                               max_tokens=8000, client=client,
                               on_token=on_token, label="critic")


# ── Judge ─────────────────────────────────────────────────────────────────────
async def judge(
    inc_text: str, bundle: list[dict], critiques: dict, client: httpx.AsyncClient,
    on_token: OnToken | None = None,
) -> dict:
    packed = json.dumps(bundle, indent=2)
    crit = json.dumps(critiques, indent=2)
    prompt = f"""{inc_text}

You are the JUDGE agent. Weigh the hypotheses, their evidence, and the critic's
attacks. Converge on the single most-supported root cause and a remediation plan.

HYPOTHESES + EVIDENCE:
{packed}

CRITIC'S ATTACKS:
{crit}

Return JSON:
{{
  "winning_hypothesis_id": <id>,
  "root_cause": "<clear statement of the root cause>",
  "confidence": <integer 0-100>,
  "why": "<2-3 sentences on why this beats the alternatives>",
  "remediation": ["<immediate action>", "<follow-up>", "..."]
}}"""
    return await generate_json(prompt, system=SYSTEM, temperature=0.2,
                               max_tokens=8000, client=client,
                               on_token=on_token, label="judge")
