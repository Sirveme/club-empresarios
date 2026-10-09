# club-empresarios

Landing de espera de **empresarios.perusistemas.pro**: bienvenida, enlaces a los
productos que ya sirven al empresario (alerta.pe, Facturalo.pro, QueVendi.pro) y un
aviso opcional (WhatsApp y/o correo, con consentimiento) para avisar cuando el
Espacio para Empresarios esté listo.

- `main.py` — FastAPI: `GET /`, `POST /api/aviso`, `GET /health`.
- `templates/index.html` — la página (tema Sepia del Club, nunca blanco).
- Variables: `DATABASE_URL` (opcional; sin ella la página responde y el formulario
  ofrece WhatsApp), `PSP_WHATSAPP` (por defecto 938246208).
- Los avisos se guardan en la tabla `empresarios_interes` (se crea sola).

Local: `uvicorn main:app --port 8001`
