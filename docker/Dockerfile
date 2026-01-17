FROM python:3.11-slim

# Metadata
LABEL maintainer="tu@email.com"
LABEL description="Sistema de Podcast TTS para artículos de FreshRSS y Wallabag"
LABEL version="3.1"

# Variables de entorno
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Europe/Madrid \
    SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.29/supercronic-linux-amd64 \
    SUPERCRONIC=supercronic-linux-amd64 \
    SUPERCRONIC_SHA1SUM=cd48d45c4b10f3f0bfdd3a57d054cd05ac96812b \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Instalar dependencias del sistema (incluyendo herramientas de red para debugging)
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    tzdata \
    ca-certificates \
    dnsutils \
    iputils-ping \
    net-tools \
    procps \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

# Instalar supercronic (cron para Docker)
RUN curl -fsSLO "$SUPERCRONIC_URL" \
    && echo "${SUPERCRONIC_SHA1SUM}  ${SUPERCRONIC}" | sha1sum -c - \
    && chmod +x "$SUPERCRONIC" \
    && mv "$SUPERCRONIC" "/usr/local/bin/${SUPERCRONIC}" \
    && ln -s "/usr/local/bin/${SUPERCRONIC}" /usr/local/bin/supercronic

# Configurar zona horaria
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Crear directorios necesarios primero
RUN mkdir -p /app /data/audio_articles /data/config /tmp

# Establecer directorio de trabajo
WORKDIR /app

# Copiar requirements
COPY requirements.txt .

# Instalar dependencias Python con mejor configuración
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    # Verificar instalaciones críticas
    python3 -c "import gtts; print('gtts OK')" && \
    python3 -c "import edge_tts; print('edge-tts OK')" && \
    python3 -c "import requests; print('requests OK')"

# Copiar scripts de la aplicación
COPY articles_to_mp3.py .
COPY podcast_server.py .
COPY docker-entrypoint.sh .
COPY update_cron.sh .

# Hacer scripts ejecutables
RUN chmod +x docker-entrypoint.sh update_cron.sh articles_to_mp3.py podcast_server.py

# Crear usuario no-root DESPUÉS de configurar archivos
RUN useradd -m -u 1000 -s /bin/bash podcast && \
    chown -R podcast:podcast /app /data /tmp

# Cambiar a usuario no-root
USER podcast

# Exponer puerto del servidor
EXPOSE 8005

# Volúmenes
VOLUME ["/data/audio_articles", "/data/config"]

# Health check mejorado
HEALTHCHECK --interval=60s --timeout=30s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8005/podcast.xml || exit 1

# Punto de entrada
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["server"]
