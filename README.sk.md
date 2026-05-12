# Gmail Attachments MCP — Docker

Production-ready MCP server pre Gmail prílohy s integrovaným web dashboardom. Multi-arch Docker image (linux/arm64 + linux/amd64).

## Čo to robí

- **MCP HTTP server** na `/mcp` — pripoj v Claude Desktop / Cowork / Code
- **Web dashboard** na `/` — OAuth login, browser príloh, MCP tester, live logy
- **Tri tools:** `list_attachments`, `download_attachment`, `extract_attachment`
- **OCR support** — pypdf pre PDF, tesseract (slk+eng) pre obrázky, alebo forward na tvoj OCR pipeline

## Štruktúra

```
.
├── app/
│   ├── main.py            # FastAPI app + OAuth routes + WebSocket logy
│   ├── mcp_server.py      # FastMCP server s tool definíciami
│   ├── gmail_service.py   # Gmail API operácie (zdieľané UI ↔ MCP)
│   ├── config.py          # Env config
│   ├── templates/
│   │   └── dashboard.html
│   └── static/
│       ├── style.css
│       └── app.js
├── Dockerfile             # Multi-arch (arm64 + amd64)
├── docker-compose.yml
├── requirements.txt
├── build.sh               # Build helper
├── .env.example
└── .dockerignore
```

## Quick start (macOS, lokálne)

```bash
# 1. Príprava
cp .env.example .env
echo "SESSION_SECRET=$(openssl rand -hex 32)" >> .env

# 2. Build & run
docker compose up --build

# 3. Otvor dashboard
open http://localhost:8765
```

V dashboarde:

1. **Setup credentials** — nahraj `credentials.json` z Google Cloud Console
   - Authorized redirect URI musí byť: `http://localhost:8765/oauth/callback`
   - Scope: `https://www.googleapis.com/auth/gmail.readonly`
2. **Sign in with Google** — klikni a autorizuj
3. **Search** v Attachment browser sekcii
4. **MCP tool tester** — debugovanie tool callov
5. **Live logs** — WebSocket stream z backendu

## Vzdialený deployment

### Možnosť A: Build priamo na cieľovom serveri
```bash
git clone https://github.com/roman-slovak/gmail-attachments-mcp.git && cd gmail-attachments-mcp
cp .env.example .env
# Nastav PUBLIC_URL na to, čo bude verejne dostupné, napr.:
#   PUBLIC_URL=http://server.local:8765
# alebo cez Tailscale:
#   PUBLIC_URL=https://gmail-mcp.<tailnet>.ts.net
nano .env
docker compose up -d --build
```

### Možnosť B: Multi-arch build z Macu, push do registry
```bash
# Na Macu
docker buildx create --name mcp-builder --use
docker buildx inspect --bootstrap
./build.sh multi ghcr.io/azazel101

# Na cieľovom serveri
docker pull ghcr.io/azazel101/gmail-attachments-mcp:latest
# Vytvor docker-compose.yml ktorý používa image: ghcr.io/azazel101/gmail-attachments-mcp:latest
docker compose up -d
```

## Google Cloud Console nastavenia

1. https://console.cloud.google.com → Create project
2. APIs & Services → Library → enable **Gmail API**
3. OAuth consent screen:
   - User Type: External
   - Scopes: `gmail.readonly`
   - Test users: pridaj svoj Gmail
4. Credentials → Create Credentials → OAuth client ID
   - Application type: **Web application**
   - Authorized redirect URIs: pridaj `<PUBLIC_URL>/oauth/callback`
   - Stiahni JSON
5. V dashboarde klikni „Upload credentials.json"

## Bezpečnosť

| Vrstva | Default | Production |
|--------|---------|------------|
| OAuth scope | `gmail.readonly` | `gmail.readonly` (nemení sa) |
| UI auth | žiadna | nastav `UI_PASSWORD` v `.env` |
| Network | `0.0.0.0:8765` | bind na Tailscale interface alebo za reverse proxy |
| HTTPS | nie | povinné pre verejnú expozíciu (Caddy / Cloudflare Tunnel) |
| Container user | UID 1000, non-root | rovnako |

Pre verejnú expozíciu odporúčam:
- **Cloudflare Tunnel + Cloudflare Access** — najjednoduchšia auth pred UI
- alebo **Tailscale** + bind na `100.x.y.z` IP — žiadny verejný endpoint

## Pripojenie z Claude Desktop / Cowork

V appke: Settings → Developer → Add custom MCP server.

```
http://server.local:8765/mcp        # LAN
https://gmail-mcp.tailnet.ts.net/mcp # Tailscale
https://gmail.tvoj-domain.sk/mcp     # cez Cloudflare Tunnel
```

## Príklady promptov

> *"Stiahni mi všetky faktúry z minulého mesiaca do priečinka faktury_2026_04."*

Claude zavolá `list_attachments(query="has:attachment subject:faktúra after:2026/04/01 before:2026/05/01")` → pre každú prílohu `download_attachment(..., subfolder="faktury_2026_04")`.

> *"Aké položky a sumy sú na dodacích listoch z dnešného rána?"*

Claude zavolá `list_attachments(query="has:attachment subject:dodací newer_than:1d")` → `extract_attachment(...)` → sumarizuje texty.

## Troubleshooting

**OAuth chyba „redirect_uri_mismatch"** — `PUBLIC_URL` v `.env` sa musí presne zhodovať s tým, čo máš v Google Cloud Console (vrátane http vs https a portu).

**Tesseract nenájde slovenčinu** — image už obsahuje `tesseract-ocr-slk`, ale ak budujeess vlastný image bez tohto baliku, slovenčina nebude fungovať.

**Token expiroval a nedá sa refreshnúť** — vymaž `data/token.json` a urob OAuth flow znova.

**MCP klient v Claude sa nepripojí** — skontroluj, že `<PUBLIC_URL>/api/health` odpovedá 200.
