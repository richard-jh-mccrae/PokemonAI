# Arena

Play a live Pokémon TCG match against this repo's agents in a browser.
Glossary: [CONTEXT.md](CONTEXT.md) · ADR-0058.

## 1. Run locally (own play / testing)

```bash
pip install -r requirements.txt        # repo root, once
python tools/arena/images.py           # once: fetch card scans (~60 MB)
cd tools
python -m uvicorn arena.server:app --port 8000
```

Open <http://localhost:8000> — pick/build a deck, play. Replays land in
`data/replays/PvC/`. Tests: `python -m pytest tests/arena/ -q`

## 2. Host machine setup (always-on box)

```bash
git clone <repo> && cd <repo>
pip install -r requirements.txt
python tools/arena/images.py
cd tools && python -m uvicorn arena.server:app --host 0.0.0.0 --port 8000
```

Keep it alive with systemd/tmux. If pytest dies with an OpenSpiel access
violation on the host: `pip uninstall open-spiel` (cabt is unaffected).

## 3. Access the hosted game

- **You (same network / VPN):** `http://<host-ip>:8000`
- **Replays back to the dev box:** `python tools/arena/pull.py user@host /path/to/repo`

### Random players — public access, free, no paid hosting

Visitors can't VPN in, but they don't have to: flip the direction. A tunnel
makes the host connect *out* to a free relay over plain HTTPS (rarely blocked,
even on corporate networks); players hit the relay's public URL. No open ports,
no VPN, no VPS.

**Quick tunnel** (zero setup, no account) — on the host:

```bash
cloudflared tunnel --url http://localhost:8000
```

Prints a public `https://….trycloudflare.com` URL anyone can open; WebSockets
(the match socket) work through it. Point the QR code at it. Catch: the URL
changes every run — fine for a session, wrong for a printed QR code.

**Stable URL** (print the QR once), either:

- **Named Cloudflare Tunnel** — free Cloudflare account; `cloudflared tunnel
  create arena`, route a hostname to it, run `cloudflared tunnel run arena` as
  a service next to uvicorn.
- **Tailscale Funnel** — install Tailscale on the host, `tailscale funnel 8000`
  → stable `https://<machine>.<tailnet>.ts.net`; visitors need nothing.

Paid hosting only makes sense if the Arena must outlive the work box.
⚠️ It is a *work* machine: exposing a service outward from the office network
is an IT-policy question — clear it before the QR code goes up.
