# Sistema de Podcast TTS - Docker 🐳

Sistema completo de podcast personal usando Docker. Convierte artículos de FreshRSS y Wallabag a MP3 y genera un feed RSS accesible desde AntennaPod.

## 🚀 Inicio Rápido (5 minutos)

```bash
# 1. Clonar o descargar los archivos
cd wallabag_rss_tts

# 2. Crear configuración
cp config.json.example_v3 config.json
nano config.json  # Editar con tus credenciales

# 3. Obtener tu IP de Tailscale
tailscale ip -4

# 4. Editar docker-compose.yml
nano docker-compose.yml
# Cambiar BASE_URL=http://TU-IP-TAILSCALE:8005

# 5. Iniciar el contenedor
docker compose up -d

# 6. Ver logs
docker compose logs -f

# 7. Añadir a AntennaPod
# URL: http://TU-IP-TAILSCALE:8005/podcast.xml
```

¡Listo! El sistema está funcionando.

## 📋 Prerequisitos

- Docker instalado
- Docker Compose instalado
- Tailscale configurado (opcional pero recomendado)
- Credenciales de FreshRSS/Wallabag

## ⚙️ Configuración

### 1. Estructura de archivos

```
podcast-tts/
├── docker-compose.yml
├── Dockerfile
├── config.json              # Tu configuración (crear desde ejemplo)
├── articles_to_mp3_v3.py
├── podcast_server.py
├── docker-entrypoint.sh
└── audio_articles/          # Se crea automáticamente
    ├── *.mp3
    └── podcast.xml
```

### 2. Configurar config.json

```bash
cp config.json.example_v3 config.json
nano config.json
```

Ejemplo mínimo:

```json
{
  "freshrss": {
    "url": "https://rss.example.com",
    "username": "tu_usuario",
    "password": "TU_CONTRASEÑA_API",
    "limit": 10,
    "categories": [
      {
        "name": "Tecnología",
        "limit": 5,
        "voice": "es-ES-ElviraNeural"
      }
    ]
  }
}
```

### 3. Configurar docker-compose.yml

Edita las variables de entorno:

```yaml
environment:
  - BASE_URL=http://100.x.x.x:8005 # ← Tu IP de Tailscale
  - PODCAST_TITLE=Mis Artículos TTS
  - CRON_SCHEDULE=0 7 * * * # 7:00 AM diario
  - DEFAULT_VOICE=es-ES-AlvaroNeural
```

## 🎮 Uso

### Comandos básicos

```bash
# Iniciar contenedor
docker compose up -d

# Ver logs en tiempo real
docker compose logs -f

# Detener contenedor
docker compose down

# Reiniciar contenedor
docker compose restart

# Ver estado
docker compose ps

# Actualizar podcast manualmente
docker compose exec podcast-tts python3 articles_to_mp3_v3.py --generate-feed

# Acceder al shell del contenedor
docker compose exec podcast-tts bash
```

### Modos de ejecución

El contenedor puede ejecutarse en diferentes modos:

**1. Servidor + Actualizaciones automáticas (predeterminado)**

```yaml
CMD ["server"]
```

- Inicia servidor HTTP en puerto 8005
- Actualiza automáticamente según CRON_SCHEDULE
- Modo recomendado para producción

**2. Solo actualización única**

```bash
docker compose run --rm podcast-tts update
```

- Actualiza una vez y termina
- Útil para testing

**3. Solo actualizaciones automáticas (sin servidor)**

```yaml
CMD ["update-loop"]
```

- Solo ejecuta cron sin servidor HTTP
- Útil si usas otro servidor web

**4. Shell interactivo**

```bash
docker compose run --rm podcast-tts bash
```

- Acceso al shell para debugging

## 📡 Acceso al Feed

Una vez iniciado:

- **Feed RSS**: `http://TU-IP-TAILSCALE:8005/podcast.xml`
- **Navegador**: `http://TU-IP-TAILSCALE:8005/`
- **Local**: `http://localhost:8005/podcast.xml`

## 🔧 Variables de Entorno

Todas configurables en `docker-compose.yml`:

| Variable              | Descripción           | Predeterminado                  |
| --------------------- | --------------------- | ------------------------------- |
| `BASE_URL`            | URL base del feed     | `http://localhost:8005`         |
| `PODCAST_TITLE`       | Título del podcast    | `Mis Artículos TTS`             |
| `PODCAST_DESCRIPTION` | Descripción           | `Artículos convertidos a audio` |
| `CRON_SCHEDULE`       | Horario actualización | `0 7 * * *` (7:00 AM)           |
| `TTS_ENGINE`          | Motor TTS             | `edge`                          |
| `DEFAULT_VOICE`       | Voz predeterminada    | `es-ES-AlvaroNeural`            |
| `TZ`                  | Zona horaria          | `Europe/Madrid`                 |

## 📁 Volúmenes

El contenedor usa volúmenes para persistir datos:

```yaml
volumes:
  - ./audio_articles:/data/audio_articles # MP3s y feed RSS
  - ./config.json:/data/config/config.json # Configuración
```

## Instalación con Docker Compose

```bash
cp .env.example .env && cp config.json.example_v3 config.json
```

Rellena `config.json` con tus credenciales (ver arriba).

Rellena `.env` (credenciales y carpetas de tu equipo) y arranca:

```bash
docker compose up -d --build
```

Los datos que genera (bases, cachés) se quedan en esta misma carpeta, fuera de git.

## Actualizaciones automáticas

El `docker-compose.yml` trae su propia [Ofelia](https://github.com/mcuadros/ofelia), que lanza dentro del contenedor los mismos trabajos y a las mismas horas que en REPEAT-ONE (formato con segundos: `seg min hora día mes día-semana`, hora de `TZ`, por defecto Europe/Madrid):

| Trabajo | Cuándo | Qué lanza |
|---|---|---|
| `podcast-tts-daily` | `0 0 17 * * *` | `python3 articles_to_mp3.py --source freshrss --tts edge --language es --generate-feed --config config.json` |

Para cambiar una hora, edita su etiqueta `ofelia.job-exec.<trabajo>.schedule` en `docker-compose.yml` y vuelve a hacer `docker compose up -d`. Para lanzarlo a mano: `docker compose exec <servicio> <orden>`. Para no tener actualizaciones automáticas: `docker compose stop ofelia`.

Esta Ofelia solo ve los contenedores de este repo (etiqueta `repeat-one.ofelia`), así que puedes tener varios módulos instalados por separado sin que se pisen. Necesita el socket de Docker en solo lectura.
