"""Quick end-to-end check of the WebSocket run flow (mirrors what the browser does)."""
import asyncio, json, collections
import websockets


async def main():
    uri = "ws://127.0.0.1:8000/ws/run"
    counts = collections.Counter()
    tokens_by_agent = collections.Counter()
    result = None
    errors = []
    async with websockets.connect(uri, max_size=None) as ws:
        await ws.send(json.dumps({}))  # empty -> server falls back to bundled sample
        async for msg in ws:
            ev = json.loads(msg)
            counts[ev["type"]] += 1
            if ev["type"] == "token":
                tokens_by_agent[ev["id"]] += 1
            elif ev["type"] == "result":
                result = ev["data"]
            elif ev["type"] == "error":
                errors.append(ev.get("detail"))

    print("event counts:", dict(counts))
    print("tokens per agent:", dict(tokens_by_agent))
    print("errors:", errors)
    if result:
        print("\nROOT CAUSE:", result.get("root_cause", "")[:90])
        print("CONFIDENCE:", result.get("confidence"))
        print("HAS _ranks:", bool(result.get("_ranks")))
        for r in result.get("_ranks", []):
            print(f"  {'★' if r['win'] else ' '} #{r['id']} {r['score']}% {r['text'][:60]}")
    else:
        print("NO RESULT RECEIVED")


asyncio.run(main())
