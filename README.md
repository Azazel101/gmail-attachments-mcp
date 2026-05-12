# Gmail Attachments MCP

> **Self-hosted MCP server that gives Claude (and any other MCP client) read-only access to your Gmail attachments — list, download, OCR, all from a chat prompt.**

A production-ready [Model Context Protocol](https://modelcontextprotocol.io/) server with an integrated web dashboard, OAuth2 (PKCE) for Gmail, multi-arch Docker image (linux/arm64 + linux/amd64), and built-in OCR for scanned invoices and screenshots.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-multiarch-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![MCP](https://img.shields.io/badge/MCP-compatible-7c3aed)](https://modelcontextprotocol.io/)

🇸🇰 **[Slovenská verzia](README.sk.md)**

---

## Why this exists

I was tired of manually downloading invoices from email every month, finding the PDF, OCR-ing it for the line items, and putting it in the right folder. So I built an MCP server that lets Claude do all of it from a single prompt:

> *"Stiahni mi všetky faktúry z apríla 2026 do priečinka faktury_2026_04 a vypíš celkovú sumu."*

Claude calls `list_attachments` → for each PDF calls `download_attachment(subfolder="faktury_2026_04")` → calls `extract_attachment` → sums the totals. Done.

## What it does

- **MCP HTTP server** at `/mcp` — connect from Claude Desktop, Claude Code, Cursor, or any other MCP client
- **Web dashboard** at `/` — OAuth login, attachment browser, MCP tool tester, live log stream over WebSocket
- **Three tools:**
  - `list_attachments(query, max_results)` — find emails matching a Gmail search query
  - `download_attachment(message_id, attachment_id, filename, subfolder)` — save to local storage
  - `extract_attachment(message_id, attachment_id, filename, use_ocr_pipeline)` — extract text from PDFs (pypdf), images (tesseract OCR with Slovak + English language packs), or forward to an external OCR service

## Quick start

```bash
git clone https://github.com/roman-slovak/gmail-attachments-mcp.git
cd gmail-attachments-mcp

cp .env.example .env
echo "SESSION_SECRET=$(openssl rand -hex 32)" >> .env

docker compose up -d --build
open http://localhost:8765
```

In the dashboard:
1. **Setup credentials** — upload `credentials.json` from Google Cloud Console
2. **Sign in with Google** — authorize once
3. **Browse / search / download** — or connect Claude Desktop to `http://localhost:8765/mcp`

Full Google Cloud Console setup (consent screen, OAuth client, redirect URI) is documented in [the Slovak README](README.sk.md#google-cloud-console-nastavenia) — same instructions, just translate the headings.

## Architecture

```
┌─────────────────┐         ┌──────────────────────────────────────┐
│  Claude Desktop │         │           Gmail MCP server           │
│  / Cowork / Code├────────►│                                      │
│   (MCP client)  │  HTTP   │  ┌──────────────┐   ┌────────────┐   │
└─────────────────┘         │  │  FastMCP     │   │  FastAPI   │   │
                            │  │  /mcp        │   │  / (UI)    │   │
┌─────────────────┐         │  │              │   │  /api/*    │   │
│   Web browser   ├────────►│  └──────┬───────┘   └─────┬──────┘   │
│   (dashboard)   │  HTTP   │         │                 │          │
└─────────────────┘         │         ▼                 ▼          │
                            │  ┌─────────────────────────────────┐ │
                            │  │     gmail_service.py            │ │
                            │  │  (shared Gmail API operations)  │ │
                            │  └────────────┬────────────────────┘ │
                            │               │                      │
                            └───────────────┼──────────────────────┘
                                            │
                                            ▼ Google OAuth2 (PKCE)
                                      ┌──────────┐
                                      │ Gmail API│
                                      └──────────┘
```

Both the MCP server and the web UI share the same `gmail_service.py` operations — there is exactly one place where Gmail API calls happen, exactly one place where attachment-extraction logic lives.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Web framework | **FastAPI** | async, OpenAPI for free, plays nicely with FastMCP |
| MCP server | **FastMCP 2.x** | least-friction way to mount MCP over HTTP under FastAPI |
| OAuth | **`google-auth-oauthlib`** with PKCE | required for installed/web flows; saved code_verifier in session |
| OCR | **tesseract-ocr (slk+eng)** + **pypdf** | local extraction, no external API dependency |
| Frontend | **Vanilla HTML + CSS + JS** | no build step, no node_modules, ~250 LoC total |
| Logs | **WebSocket stream** (deque buffer) | live dashboard log tailing without external services |
| Container | **multi-arch Docker** (arm64 + amd64) | runs identically on ARM SBCs and x86 servers |
| Reverse proxy | **uvicorn `--proxy-headers`** | ready behind Cloudflare Tunnel, Tailscale Funnel, Caddy |

## Remote deployment

```bash
git clone https://github.com/roman-slovak/gmail-attachments-mcp.git
cd gmail-attachments-mcp
cp .env.example .env

# Set PUBLIC_URL to whatever is reachable from your MCP client:
#   http://server.local:8765
#   https://gmail-mcp.<tailnet>.ts.net      (Tailscale)
#   https://gmail.your-domain.com           (Cloudflare Tunnel)
nano .env

docker compose up -d --build
```

For multi-arch builds (e.g. building amd64 + arm64 from a Mac) and `ghcr.io` push, see `build.sh`.

## Security model

| Layer | Default (LAN) | Recommended for public exposure |
|---|---|---|
| OAuth scope | `gmail.readonly` | `gmail.readonly` (immutable) |
| UI auth | none | set `UI_PASSWORD` (HTTP Basic) |
| Network bind | `0.0.0.0:8765` | bind to Tailscale interface only |
| TLS | none | required — use Caddy or Cloudflare Tunnel |
| Container user | UID 1000, non-root | same |

For public exposure I recommend **Cloudflare Tunnel + Cloudflare Access** (zero-config auth in front of the UI) or **Tailscale Funnel** (no public endpoint at all).

## Connecting MCP clients

In Claude Desktop / Claude Code / Cursor: *Settings → Developer → Add custom MCP server*.

```
http://localhost:8765/mcp                 # local
http://server.local:8765/mcp              # LAN
https://gmail-mcp.tailnet.ts.net/mcp      # Tailscale
https://gmail.your-domain.com/mcp         # via tunnel
```

Once connected, Claude has access to the three Gmail tools and you can start prompting:

> *"Stiahni mi všetky faktúry z minulého mesiaca do priečinka faktury_2026_04."*
>
> *"Aké položky a sumy sú na dodacích listoch z dnešného rána?"*
>
> *"Find the latest contract PDF from any sender at acme.com and summarize the termination clauses."*

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `redirect_uri_mismatch` | `PUBLIC_URL` in `.env` must exactly match the redirect URI in Google Cloud Console (scheme, host, port, path) |
| `invalid_grant: Missing code verifier` | PKCE code_verifier was lost between `/oauth/start` and `/oauth/callback` — fixed in this codebase by saving it to the session |
| Tesseract can't OCR Slovak | image already includes `tesseract-ocr-slk`; if you build a custom image, install it |
| Token expired and won't refresh | delete `data/token.json` and re-run the OAuth flow |
| MCP client won't connect | check `<PUBLIC_URL>/api/health` returns 200 and `authenticated: true` |

## Project structure

```
.
├── app/
│   ├── main.py            # FastAPI app, OAuth routes, WebSocket logs
│   ├── mcp_server.py      # FastMCP server with tool definitions
│   ├── gmail_service.py   # Shared Gmail API operations (UI ↔ MCP)
│   ├── config.py          # Env-based config
│   ├── templates/
│   │   └── dashboard.html
│   └── static/
│       ├── style.css
│       └── app.js
├── Dockerfile             # Multi-arch (arm64 + amd64)
├── docker-compose.yml
├── requirements.txt
├── build.sh               # Multi-arch build helper
├── .env.example
├── .dockerignore
├── README.md              # English (this file)
└── README.sk.md           # Slovak version
```

## Author

Built by **Roman Slovák**.

- GitHub: [@roman-slovak](https://github.com/roman-slovak)
- LinkedIn: [Roman Slovák](https://www.linkedin.com/in/roman-slovak-6062ba29/)
- Email: roman.slovak@gmail.com

## License

MIT — see [LICENSE](LICENSE).
