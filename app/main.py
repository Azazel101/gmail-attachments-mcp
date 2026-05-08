"""
Gmail Attachments MCP - main FastAPI application.

Combines:
  - Web dashboard (login, attachment browser, MCP tester, logs)
  - Google OAuth flow for Gmail authentication
  - MCP HTTP server mounted at /mcp
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google_auth_oauthlib.flow import Flow
from starlette.middleware.sessions import SessionMiddleware

from . import config, gmail_service
from .mcp_server import mcp

# ---------- Logging - keep last N entries in memory for the UI ----------
LOG_BUFFER: deque[str] = deque(maxlen=500)
LOG_SUBSCRIBERS: set[asyncio.Queue[str]] = set()


class BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        LOG_BUFFER.append(msg)
        for q in list(LOG_SUBSCRIBERS):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.LOG_PATH),
        BufferHandler(),
    ],
)
LOG = logging.getLogger("gmail-mcp.app")


# Build the MCP HTTP sub-app first so we can inherit its lifespan
mcp_app = mcp.http_app(path="/")


# ---------- Lifespan ----------
# FastMCP's HTTP app provides its own lifespan (session manager, etc.) that
# MUST be invoked when mounted under FastAPI - otherwise the MCP endpoint 500s.
# We chain our startup logging through the MCP lifespan.
@asynccontextmanager
async def lifespan(app: FastAPI):
    LOG.info("Starting Gmail Attachments MCP")
    LOG.info("Data dir: %s", config.DATA_DIR)
    LOG.info("Public URL: %s", config.PUBLIC_URL)
    LOG.info("Authenticated: %s", gmail_service.is_authenticated())
    async with mcp_app.lifespan(app):
        yield
    LOG.info("Shutting down")


app = FastAPI(title="Gmail Attachments MCP", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET)

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ---------- Optional HTTP Basic auth for the UI ----------
basic = HTTPBasic(auto_error=False)


def require_ui_auth(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(basic)],
) -> bool:
    """Voliteľná HTTP Basic ochrana web UI (zapnutá ak je UI_PASSWORD nastavené)."""
    if not config.UI_PASSWORD:
        return True
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth required",
            headers={"WWW-Authenticate": "Basic"},
        )
    user_ok = secrets.compare_digest(credentials.username, config.UI_USERNAME)
    pwd_ok = secrets.compare_digest(credentials.password, config.UI_PASSWORD)
    if not (user_ok and pwd_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bad credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


# ---------- Web UI routes ----------
@app.get("/", response_class=HTMLResponse)
def index(request: Request, _: bool = Depends(require_ui_auth)):
    auth = gmail_service.is_authenticated()
    user_email = gmail_service.get_user_email() if auth else None
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "authenticated": auth,
            "user_email": user_email,
            "has_credentials": config.CREDENTIALS_PATH.exists(),
            "public_url": config.PUBLIC_URL,
            "mcp_url": f"{config.PUBLIC_URL}/mcp",
        },
    )


# ---------- OAuth flow ----------
@app.get("/oauth/start")
def oauth_start(request: Request, _: bool = Depends(require_ui_auth)):
    if not config.CREDENTIALS_PATH.exists():
        raise HTTPException(
            status_code=400,
            detail=(
                "credentials.json not found in data dir. Upload it first via the "
                "'Setup credentials' section in the dashboard."
            ),
        )

    flow = Flow.from_client_secrets_file(
        str(config.CREDENTIALS_PATH),
        scopes=config.SCOPES,
        redirect_uri=config.OAUTH_REDIRECT_URI,
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    request.session["oauth_state"] = state
    request.session["oauth_code_verifier"] = flow.code_verifier
    return RedirectResponse(auth_url)


@app.get(config.OAUTH_REDIRECT_PATH)
def oauth_callback(request: Request, code: str = "", state: str = ""):
    saved_state = request.session.get("oauth_state")
    if not saved_state or saved_state != state:
        raise HTTPException(status_code=400, detail="OAuth state mismatch")

    flow = Flow.from_client_secrets_file(
        str(config.CREDENTIALS_PATH),
        scopes=config.SCOPES,
        redirect_uri=config.OAUTH_REDIRECT_URI,
        state=saved_state,
    )
    code_verifier = request.session.get("oauth_code_verifier")
    if code_verifier:
        flow.code_verifier = code_verifier
    flow.fetch_token(code=code)
    creds = flow.credentials
    config.TOKEN_PATH.write_text(creds.to_json())
    LOG.info("OAuth completed - token saved")
    return RedirectResponse("/")


@app.post("/oauth/logout")
def oauth_logout(_: bool = Depends(require_ui_auth)):
    if config.TOKEN_PATH.exists():
        config.TOKEN_PATH.unlink()
        LOG.info("Token deleted (logout)")
    return RedirectResponse("/", status_code=303)


# ---------- Credentials upload ----------
@app.post("/credentials/upload")
async def upload_credentials(
    request: Request, _: bool = Depends(require_ui_auth)
):
    """Nahraj credentials.json cez web UI (alternatíva k vloženiu cez volume)."""
    form = await request.form()
    upload = form.get("file")
    if upload is None:
        raise HTTPException(status_code=400, detail="No file")
    content = await upload.read()
    config.CREDENTIALS_PATH.write_bytes(content)
    LOG.info("credentials.json uploaded (%d bytes)", len(content))
    return RedirectResponse("/", status_code=303)


# ---------- Browser API (for the dashboard) ----------
@app.get("/api/list")
def api_list(
    query: str = Query("has:attachment newer_than:7d"),
    max_results: int = Query(20, ge=1, le=50),
    _: bool = Depends(require_ui_auth),
):
    if not gmail_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return gmail_service.list_attachments_op(query=query, max_results=max_results)
    except Exception as exc:
        LOG.exception("list failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/download")
async def api_download(request: Request, _: bool = Depends(require_ui_auth)):
    if not gmail_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    body = await request.json()
    try:
        return gmail_service.download_attachment_op(
            message_id=body["message_id"],
            attachment_id=body["attachment_id"],
            filename=body["filename"],
            subfolder=body.get("subfolder"),
        )
    except Exception as exc:
        LOG.exception("download failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/extract")
async def api_extract(request: Request, _: bool = Depends(require_ui_auth)):
    if not gmail_service.is_authenticated():
        raise HTTPException(status_code=401, detail="Not authenticated")
    body = await request.json()
    try:
        return gmail_service.extract_attachment_op(
            message_id=body["message_id"],
            attachment_id=body["attachment_id"],
            filename=body["filename"],
            use_ocr_pipeline=body.get("use_ocr_pipeline", False),
        )
    except Exception as exc:
        LOG.exception("extract failed")
        raise HTTPException(status_code=500, detail=str(exc))


# ---------- Health ----------
@app.get("/api/health")
def health():
    return {
        "ok": True,
        "authenticated": gmail_service.is_authenticated(),
        "user": gmail_service.get_user_email(),
    }


# ---------- Logs ----------
@app.get("/api/logs")
def get_logs(_: bool = Depends(require_ui_auth)):
    return {"logs": list(LOG_BUFFER)}


@app.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    # Pre WS jednoducho iba zapneme stream; UI auth sa rieši pri loadovaní stránky.
    await websocket.accept()
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=200)
    LOG_SUBSCRIBERS.add(queue)
    try:
        # Pošli celý buffer hneď
        for msg in list(LOG_BUFFER):
            await websocket.send_text(msg)
        while True:
            msg = await queue.get()
            await websocket.send_text(msg)
    except WebSocketDisconnect:
        pass
    finally:
        LOG_SUBSCRIBERS.discard(queue)


# ---------- Mount MCP server ----------
# FastMCP's HTTP app is mounted under /mcp; external MCP clients connect to
# {PUBLIC_URL}/mcp. The lifespan was already chained above.
app.mount("/mcp", mcp_app)
