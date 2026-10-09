"""
empresarios.perusistemas.pro — landing de espera del Espacio para Empresarios.

Una sola pagina: bienvenida, mensaje honesto ("lo estamos construyendo"), enlaces a
los productos que YA sirven al empresario y un aviso OPCIONAL (WhatsApp y/o correo,
con consentimiento) para avisarle cuando el espacio este listo.

Si DATABASE_URL no esta configurada, la pagina igual responde; el formulario
ofrece escribir por WhatsApp en vez de guardar.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

BASE = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
PSP_WHATSAPP = "".join(c for c in os.getenv("PSP_WHATSAPP", "938246208") if c.isdigit())
CONSENT_VER = "empresarios-aviso-2026-10-09"
LIMITE_IP_HORA = 5
_CORREO_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
log = logging.getLogger("uvicorn.error")
_pool: asyncpg.Pool | None = None

ESQUEMA = """
CREATE TABLE IF NOT EXISTS empresarios_interes (
    id                 bigserial PRIMARY KEY,
    whatsapp           text,
    correo             text,
    consentimiento_en  timestamptz NOT NULL,
    consentimiento_ver text NOT NULL,
    origen             text,
    ip                 inet,
    user_agent         text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_interes_contacto CHECK (whatsapp IS NOT NULL OR correo IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_interes_whatsapp ON empresarios_interes (whatsapp) WHERE whatsapp IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_interes_correo ON empresarios_interes (lower(correo)) WHERE correo IS NOT NULL;
"""

PRODUCTOS = [
    {"nombre": "alerta.pe", "url": "https://alerta.pe/empresarios", "color": "cobre",
     "que": "Vigila tu Buzón SUNAT y SUNAFIL",
     "por": "Te avisa apenas llega una notificación, para que nunca te enteres tarde de una multa."},
    {"nombre": "Facturalo.pro", "url": "https://facturalo.pro/", "color": "turquesa",
     "que": "Facturación electrónica SUNAT",
     "por": "Emite facturas y boletas en segundos, desde S/29 al mes."},
    {"nombre": "QueVendi.pro", "url": "https://quevendi.pro/", "color": "salvia",
     "que": "Punto de venta para tu negocio",
     "por": "Vende, cobra, emite tus comprobantes y lleva tu caja al día."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pool
    if DATABASE_URL:
        try:
            _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
            await _pool.execute(ESQUEMA)
        except Exception:
            log.exception("Sin base de datos: la landing sigue, sin guardar avisos.")
            _pool = None
    yield
    if _pool is not None:
        await _pool.close()


app = FastAPI(title="Espacio para Empresarios", lifespan=lifespan, docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory=str(BASE / "templates"))


def _ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for", "")
    cand = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "")
    try:
        return str(ipaddress.ip_address(cand)) if cand else None
    except ValueError:
        return None


def _whatsapp(raw) -> str | None:
    d = "".join(c for c in str(raw or "") if c.isdigit())
    if d.startswith("51") and len(d) == 11:
        d = d[2:]
    return d if len(d) == 9 and d.startswith("9") else None


@app.get("/", response_class=HTMLResponse)
async def inicio(request: Request, ref: str = ""):
    return templates.TemplateResponse(request, "index.html", {
        "productos": PRODUCTOS, "guarda": _pool is not None, "wa": PSP_WHATSAPP, "origen": (ref or "landing")[:60]})


@app.post("/api/aviso")
async def aviso(payload: dict, request: Request):
    if (payload.get("empresa_web") or "").strip():           # honeypot
        return JSONResponse({"ok": True})
    wa_raw, correo = (payload.get("whatsapp") or "").strip(), (payload.get("correo") or "").strip().lower()
    whatsapp = _whatsapp(wa_raw)
    if wa_raw and not whatsapp:
        return JSONResponse({"ok": False, "error": "El WhatsApp tiene 9 dígitos y empieza en 9."}, status_code=422)
    if correo and not _CORREO_RE.match(correo):
        return JSONResponse({"ok": False, "error": "Revisa tu correo."}, status_code=422)
    if not whatsapp and not correo:
        return JSONResponse({"ok": False, "error": "Déjanos al menos tu WhatsApp o tu correo."}, status_code=422)
    if not payload.get("consentimiento"):
        return JSONResponse({"ok": False, "error": "Marca la autorización para poder avisarte."}, status_code=422)
    if _pool is None:
        return JSONResponse({"ok": False, "error": f"Por ahora escríbenos al WhatsApp {PSP_WHATSAPP} y te avisamos."},
                            status_code=503)
    ip = _ip(request)
    if ip and await _pool.fetchval("SELECT count(*) FROM empresarios_interes WHERE ip = $1::inet "
                                   "AND created_at > now() - interval '1 hour'", ip) >= LIMITE_IP_HORA:
        return JSONResponse({"ok": False, "error": "Recibimos varios avisos desde tu red. Intenta más tarde."},
                            status_code=429)
    try:
        await _pool.execute(
            "INSERT INTO empresarios_interes (whatsapp, correo, consentimiento_en, consentimiento_ver, origen, ip, "
            "user_agent) VALUES ($1, $2, now(), $3, $4, $5::inet, $6)",
            whatsapp, correo or None, CONSENT_VER, (payload.get("origen") or "landing")[:60], ip,
            (request.headers.get("user-agent") or "")[:400] or None)
    except asyncpg.UniqueViolationError:
        pass                                                 # ya estaba: no se duplica ni se revela
    return JSONResponse({"ok": True, "mensaje": "¡Listo! Te avisaremos apenas tu espacio esté listo."})


@app.get("/health")
async def health():
    return {"ok": True, "guarda_avisos": _pool is not None}
