# CLAUDE.md

## Qué hace

`server.py` es un backend Flask (`/api/*`) para seleccionar artículos de
FreshRSS/Wallabag y convertirlos a MP3 (TTS) para escucharlos como podcast.
La UI estática (`index.html`, `web/`) y el feed RSS/los MP3 generados
(`podcast.xml`, `audio_articles/`) los sirve **nginx directamente** (SWAG),
no Flask — `server.py` solo atiende `/api/*` y `/health`.

La conversión real la hacen `process_selection.py` (selección manual desde
la web) y `articles_to_mp3.py` (cron diario, ver más abajo); `convert_url.py`
convierte una URL suelta. `server.py` los lanza como subprocesos, todos
deben vivir en el mismo directorio (`WORK_DIR`) — ver más abajo.

## Docker (repeat-one) vs despliegue nativo

Hasta 2026-08 esto corría **fuera de Docker**, como servicio systemd
(`podcast-tts-web.service`) + una entrada de crontab para la conversión
diaria, en `~/contenedores/podcast-tts` en el host. Ya está migrado a
Docker como submodule de `repeat-one` (`services/podcast_tts`), pero con
una particularidad importante:

**El código va en la imagen (`COPY . .`), pero los datos reales se montan
individualmente desde su ubicación física original** (`~/contenedores/
podcast-tts/config.json`, `/audio_articles`, etc.) — no se copiaron ni
duplicaron. Motivo: SWAG sirve los estáticos (`index.html`, `podcast.xml`,
`audio_articles/`) directamente desde esa misma ruta del host
(`root /config/www/podcast-tts` en su config de nginx, bind-mount de
`~/contenedores/podcast-tts` completo) — si los datos vivieran solo dentro
del contenedor, SWAG dejaría de verlos. Migrar esa parte de SWAG también
era una opción, pero cambiar el mínimo posible en un servicio en uso reduce
el riesgo; queda documentado aquí por si se quiere limpiar más adelante.

`WORK_DIR` en `server.py` es `$PODCAST_WORK_DIR` (Docker: `/app`, que es
donde caen los mounts de datos) con fallback al path nativo de siempre si
la variable no está — para poder seguir arrancándolo fuera de Docker sin
cambios si hiciera falta.

## Cron diario

Antes una entrada de `crontab` (`0 17 * * * ... articles_to_mp3.py
--source freshrss --tts edge --language es --generate-feed --config
config.json --mark-as-read`). En `repeat-one` es un
`ofelia.job-exec` en `docker-compose.yml`, mismo patrón que el resto de
servicios del proyecto.

## El `docker/` que había antes

El repo ya traía un intento previo de dockerización (`docker/Dockerfile`,
`docker/docker-compose.yml`, `docker/podcast_server.py`) que **no se usó**:
`podcast_server.py` (unas 60 líneas) no es ni de lejos el mismo servidor
que `server.py` (500+ líneas) — le faltan rutas enteras (`/api/convert-url`,
`/api/config`, cola de conversión, etc.) y no incluye `process_selection.py`
ni `convert_url.py` en la imagen. Se ha borrado y sustituido por un
`Dockerfile` en la raíz que sí empaqueta el código real.
