"""The Arena web app: FastAPI + one WebSocket per Table (ADR-0033).

REST carries the funnel (presets, Deck Text checking, table creation, the Rating);
the WebSocket carries the match — view-model frames out, choices in. The server
builds every view server-side (arena.view); the browser is a dumb renderer.

Run:  uvicorn arena.server:app --host 0.0.0.0 --port 8000   (from tools/)
"""
from __future__ import annotations

import asyncio
import json
import random
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

_TOOLS = Path(__file__).resolve().parents[1]
_REPO = _TOOLS.parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from arena import decks, images, replay_store, view  # noqa: E402
from arena.tables import TableFull, TableManager  # noqa: E402

_STATIC = Path(__file__).resolve().parent / "static"
_AGENTS_ROOT = _REPO / "src" / "agents"

_NAME_CAP = 40
_TEXT_CAP = 2000
_DECK_TEXT_CAP = 20_000
_PHASES = {None, "early", "mid", "late"}


def _clean(value, cap: int) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:cap] if value else None


def _playable_agents(agents_root: Path) -> list[str]:
    return sorted(d.name for d in agents_root.iterdir()
                  if (d / "main.py").is_file() and (d / "deck.csv").is_file())


def create_app(*, replay_dir: Path | None = None, cap: int = 4,
               idle_timeout: float = 600, worker_cmd: list[str] | None = None,
               agents_root: Path | None = None, sweep_interval: float = 30,
               images_dir: Path | None = None, prewarm: bool = True) -> FastAPI:
    replay_dir = Path(replay_dir) if replay_dir else replay_store.REPLAY_DIR
    agents_root = Path(agents_root) if agents_root else _AGENTS_ROOT
    images_dir = Path(images_dir) if images_dir else images.CARDS_DIR
    # startup snapshot — run tools/arena/images.py then restart to pick up new scans
    have_image = ({int(p.stem) for p in images_dir.glob("*.png") if p.stem.isdigit()}
                  if images_dir.is_dir() else set())

    def _pick_warm():
        # random per warm spawn — the standby IS the random matchmaking draw
        agents = _playable_agents(agents_root)
        name = random.choice(agents)
        return name, agents_root / name

    manager = TableManager(replay_dir=replay_dir, cap=cap, idle_timeout=idle_timeout,
                           worker_cmd=worker_cmd,
                           warm_picker=_pick_warm if prewarm else None)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async def sweeper():
            while True:
                await asyncio.sleep(sweep_interval)
                await asyncio.to_thread(manager.sweep)   # locks/pipes stay off the loop
        task = asyncio.create_task(sweeper())
        try:
            yield
        finally:
            task.cancel()
            await asyncio.to_thread(manager.shutdown)

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=2048)   # the catalog is ~0.5 MB raw

    @app.middleware("http")
    async def limit_body(request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > 64_000:
            return JSONResponse({"error": "request too large"}, status_code=413)
        return await call_next(request)

    # -- funnel ---------------------------------------------------------------

    @app.get("/api/presets")
    def presets():
        return {"presets": [{"id": p.id, "title": p.title} for p in decks.list_presets()]}

    @app.get("/api/presets/{preset_id}")
    def preset_detail(preset_id: str):
        try:
            cards = decks.preset_cards(preset_id)
        except KeyError:
            return JSONResponse({"error": "unknown preset"}, status_code=404)
        return {"id": preset_id, "title": preset_id.replace("_", " "), "cards": cards}

    @app.get("/api/cards")
    def cards():
        return {"cards": [{**c, "img": c["id"] in have_image}
                          for c in decks.pool_catalog()]}

    def _ids_from(body: dict) -> list[int] | None:
        raw = body.get("ids") if "ids" in body else body.get("deck_ids")
        if not isinstance(raw, list) or len(raw) > 400:
            return None
        try:
            return [int(i) for i in raw]
        except (TypeError, ValueError):
            return None

    @app.post("/api/deck")
    def check_deck(body: dict):
        if "ids" in body:
            ids = _ids_from(body)
            res = (decks.validate_ids(ids) if ids is not None
                   else decks.DeckResult(problems=("not a card id list",)))
        else:
            res = decks.resolve_deck_text(_clean(body.get("text"), _DECK_TEXT_CAP) or "")
        if res.ok:
            return {"ok": True, "cards": len(res.ids)}
        return {"ok": False, "problems": list(res.problems)}

    @app.post("/api/tables")
    def create_table(body: dict):
        agents = _playable_agents(agents_root)
        # unnamed -> the pre-warmed standby's bot (its agent was drawn randomly at
        # warm time), falling back to a fresh random draw when no standby exists
        warm = manager.warm_agent()
        agent = body.get("agent") or (warm if warm in agents else None) \
            or (random.choice(agents) if agents else None)
        if agent not in agents:
            return JSONResponse({"error": f"unknown agent {agent!r}"}, status_code=404)
        if "deck_ids" in body:                     # the in-app builder's list
            ids = _ids_from(body)
            res = (decks.validate_ids(ids) if ids is not None
                   else decks.DeckResult(problems=("not a card id list",)))
        elif body.get("preset"):
            try:
                res = decks.load_preset(str(body["preset"]))
            except KeyError:
                return JSONResponse({"error": "unknown preset"}, status_code=404)
        else:
            res = decks.resolve_deck_text(_clean(body.get("deck_text"), _DECK_TEXT_CAP) or "")
        if not res.ok:
            return JSONResponse({"problems": list(res.problems)}, status_code=400)
        try:
            table = manager.create(
                visitor=_clean(body.get("visitor"), _NAME_CAP), deck=list(res.ids),
                agent_name=agent, agent_dir=agents_root / agent)
        except TableFull:
            return JSONResponse({"error": "all tables are taken — try again in a few minutes"},
                                status_code=409)
        return {"table_id": table.id, "agent": agent}

    # -- post-game ------------------------------------------------------------

    @app.post("/api/tables/{table_id}/rating")
    def rate(table_id: str, body: dict):
        try:
            table = manager.get(table_id)
        except KeyError:
            return JSONResponse({"error": "unknown table"}, status_code=404)
        if table.state != "over" or not table.replay_path:
            return JSONResponse({"error": "match not finished"}, status_code=409)
        phase = body.get("phase")
        if not isinstance(phase, str) or phase not in _PHASES:
            phase = None
        replay_store.patch_rating(Path(table.replay_path), {
            "misplay": _clean(body.get("misplay"), _TEXT_CAP),
            "phase": phase,
            "comments": _clean(body.get("comments"), _TEXT_CAP),
        })
        return {"ok": True}

    # -- the match socket -------------------------------------------------------

    def _end_payload(table) -> dict:
        end = table.end_info or {}
        if end.get("kind") == "died":       # the worker crashed — no result to claim
            return {"type": "end", "error": True, "you_won": False, "draw": False,
                    "forfeit": table.forfeit}
        rewards = end.get("rewards") or [None, None]
        human = rewards[0] if len(rewards) > 0 else None   # the Visitor holds seat 0
        return {
            "type": "end",
            "you_won": human == 1,
            "draw": all(r == 0 for r in rewards) if None not in rewards else False,
            "forfeit": table.forfeit,
        }

    @app.websocket("/ws/{table_id}")
    async def match_socket(ws: WebSocket, table_id: str):
        # accept first: a close() before the handshake surfaces as a bare HTTP 403
        # under real uvicorn and the browser never sees why.
        await ws.accept()
        try:
            table = manager.get(table_id)
        except KeyError:
            await ws.send_json({"type": "error", "error": "unknown table"})
            await ws.close(code=4404)
            return

        async def pump_out():
            # Snapshot model: each connection tracks the seq it has rendered, so
            # reconnects replay the current state exactly once and can never steal
            # a frame from another connection. Short waits keep an abandoned
            # to_thread worker from outliving its socket by more than a few seconds.
            seen = 0
            while True:
                snap = await asyncio.to_thread(table.wait_change, seen, 5.0)
                if snap is None:
                    continue
                seen = snap["seq"]
                if snap["state"] == "over":
                    await ws.send_json(_end_payload(table))
                    return
                if snap["state"] == "acting" and snap["obs"] is not None:
                    await ws.send_json({"type": "state",
                                        "view": view.build_view(snap["obs"])})
                elif snap["state"] == "thinking":
                    await ws.send_json({"type": "thinking"})

        out = asyncio.create_task(pump_out())
        try:
            while not out.done():
                receive = asyncio.create_task(ws.receive_text())
                done, _ = await asyncio.wait({receive, out},
                                             return_when=asyncio.FIRST_COMPLETED)
                if receive not in done:
                    receive.cancel()
                    continue
                try:
                    msg = json.loads(receive.result())
                except ValueError:
                    continue                # garbage in, match unharmed
                if not isinstance(msg, dict):
                    continue
                if msg.get("type") == "choose":
                    try:
                        indices = [int(i) for i in msg.get("indices") or []][:200]
                    except (TypeError, ValueError):
                        continue
                    await asyncio.to_thread(manager.choose, table_id, indices)
                elif msg.get("type") == "concede":
                    await asyncio.to_thread(manager.concede, table_id)
        except (WebSocketDisconnect, RuntimeError):
            pass                            # the sweep reclaims an abandoned Table
        finally:
            if not out.done():
                out.cancel()

    if images_dir.is_dir():
        app.mount("/cards", StaticFiles(directory=images_dir), name="cards")
    if _STATIC.is_dir():
        app.mount("/", StaticFiles(directory=_STATIC, html=True), name="static")
    return app


app = create_app()
