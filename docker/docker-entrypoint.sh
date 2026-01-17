#!/bin/bash
set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}    Sistema de Podcast TTS - Docker${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"

# Configuración por defecto
CONFIG_FILE="${CONFIG_FILE:-/data/config/config.json}"
AUDIO_DIR="${AUDIO_DIR:-/data/audio_articles}"
BASE_URL="${BASE_URL:-http://localhost:8005}"
CRON_SCHEDULE="${CRON_SCHEDULE:-0 7 * * *}"
TTS_ENGINE="${TTS_ENGINE:-gtts}"
DEFAULT_VOICE="${DEFAULT_VOICE:-es-ES-AlvaroNeural}"
DEBUG="${DEBUG:-0}"

# Función de log mejorada
log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a /tmp/podcast.log
}

# Verificar conectividad de red
check_network() {
    log "${YELLOW}Verificando conectividad de red...${NC}"

    # Test DNS
    if nslookup google.com > /dev/null 2>&1; then
        log "${GREEN}✓ DNS funciona correctamente${NC}"
    else
        log "${RED}✗ DNS no funciona - puede haber problemas de red${NC}"
        log "${YELLOW}  Intentando con IP directa...${NC}"
        if ping -c 1 8.8.8.8 > /dev/null 2>&1; then
            log "${GREEN}✓ Conectividad IP funciona${NC}"
            log "${YELLOW}⚠️  Problema con DNS, considera cambiar DNS en docker-compose${NC}"
        else
            log "${RED}✗ No hay conectividad de red${NC}"
            return 1
        fi
    fi

    # Test HTTPS
    if curl -s --connect-timeout 5 https://www.google.com > /dev/null 2>&1; then
        log "${GREEN}✓ Conectividad HTTPS funciona${NC}"
    else
        log "${YELLOW}⚠️  Problemas con HTTPS${NC}"
    fi

    return 0
}

# Verificar que existe el archivo de configuración
if [ ! -f "$CONFIG_FILE" ]; then
    log "${RED}✗ Error: No se encuentra config.json en /data/config/${NC}"
    log "${YELLOW}  Crea el archivo config.json usando config_EXAMPLE.json como plantilla${NC}"
    exit 1
fi

log "${GREEN}✓ Archivo de configuración encontrado${NC}"

# Validar JSON
if python3 -c "import json; json.load(open('$CONFIG_FILE'))" 2>/dev/null; then
    log "${GREEN}✓ config.json es válido${NC}"
else
    log "${RED}✗ config.json tiene errores de sintaxis${NC}"
    exit 1
fi

# Crear directorio de audio si no existe
mkdir -p "$AUDIO_DIR"
log "${GREEN}✓ Directorio de audio: ${AUDIO_DIR}${NC}"

# Verificar permisos de escritura
if touch "$AUDIO_DIR/.test" 2>/dev/null; then
    rm "$AUDIO_DIR/.test"
    log "${GREEN}✓ Permisos de escritura OK${NC}"
else
    log "${RED}✗ No hay permisos de escritura en $AUDIO_DIR${NC}"
    exit 1
fi

# Verificar conectividad
check_network || log "${YELLOW}⚠️  Continuando a pesar de problemas de red...${NC}"

# Verificar que edge-tts esté disponible si se solicita
if [ "$TTS_ENGINE" = "edge" ]; then
    if python3 -c "import edge_tts" 2>/dev/null; then
        log "${GREEN}✓ edge-tts instalado y disponible${NC}"

        # Test de conectividad a servicios de Microsoft
        log "${YELLOW}Probando conectividad con Microsoft TTS...${NC}"
        if timeout 10 python3 -c "import asyncio; import edge_tts; asyncio.run(edge_tts.list_voices())" > /dev/null 2>&1; then
            log "${GREEN}✓ Microsoft TTS accesible${NC}"
        else
            log "${RED}✗ No se puede conectar a Microsoft TTS${NC}"
            log "${YELLOW}  Cambiando a gtts...${NC}"
            TTS_ENGINE="gtts"
        fi
    else
        log "${RED}✗ edge-tts no está instalado${NC}"
        log "${YELLOW}  Usando gtts como alternativa...${NC}"
        TTS_ENGINE="gtts"
    fi
fi

# Función para actualizar el podcast
update_podcast() {
    log "${YELLOW}=== Inicio de actualización del podcast ===${NC}"
    log "Motor TTS: $TTS_ENGINE"
    log "Voz: $DEFAULT_VOICE"
    log "Config: $CONFIG_FILE"
    log "Output: $AUDIO_DIR"

    cd /app

    # Ejecutar con timeout y manejo de errores
    if timeout 600 python3 articles_to_mp3.py \
        --config "$CONFIG_FILE" \
        --output "$AUDIO_DIR" \
        --tts "$TTS_ENGINE" \
        --voice "$DEFAULT_VOICE" \
        --generate-feed \
        --base-url "$BASE_URL" \
        --feed-title "${PODCAST_TITLE:-Mis Artículos TTS}" \
        --feed-description "${PODCAST_DESCRIPTION:-Artículos convertidos a audio}" \
        2>&1 | tee -a /tmp/podcast_update.log; then

        log "${GREEN}✓ Actualización completada exitosamente${NC}"

        # Verificar que se creó el feed
        if [ -f "$AUDIO_DIR/podcast.xml" ]; then
            log "${GREEN}✓ Feed RSS creado: $AUDIO_DIR/podcast.xml${NC}"
            MP3_COUNT=$(find "$AUDIO_DIR" -name "*.mp3" 2>/dev/null | wc -l)
            log "${GREEN}✓ Total de MP3s: $MP3_COUNT${NC}"
        else
            log "${RED}✗ No se creó el feed RSS${NC}"
            log "${YELLOW}  Revisa los logs en /tmp/podcast_update.log${NC}"
        fi
    else
        EXIT_CODE=$?
        if [ $EXIT_CODE -eq 124 ]; then
            log "${RED}✗ Timeout: La actualización tardó más de 10 minutos${NC}"
        else
            log "${RED}✗ Error en la actualización (código: $EXIT_CODE)${NC}"
        fi
        log "${YELLOW}  Revisa los logs en /tmp/podcast_update.log${NC}"
        return 1
    fi

    log "${YELLOW}=== Fin de actualización del podcast ===${NC}"
    echo "" >> /tmp/podcast_update.log
}

# Función para iniciar el servidor
start_server() {
    log "${GREEN}✓ Iniciando servidor HTTP en puerto 8005...${NC}"
    log "${GREEN}  URL base: ${BASE_URL}${NC}"
    log "${GREEN}  Feed RSS: ${BASE_URL}/podcast.xml${NC}"
    log "${GREEN}  Directorio: ${AUDIO_DIR}${NC}"

    # Asegurar que el directorio existe
    mkdir -p "$AUDIO_DIR"

    cd "$AUDIO_DIR"
    exec python3 /app/podcast_server.py --host 0.0.0.0 --port 8005 --dir .
}

# Configurar cron
setup_cron() {
    log "${GREEN}✓ Configurando actualización automática...${NC}"
    log "${YELLOW}  Horario: ${CRON_SCHEDULE}${NC}"

    # Crear script de actualización
    cat > /tmp/update_script.sh << 'EOFSCRIPT'
#!/bin/bash
export CONFIG_FILE="${CONFIG_FILE}"
export AUDIO_DIR="${AUDIO_DIR}"
export BASE_URL="${BASE_URL}"
export TTS_ENGINE="${TTS_ENGINE}"
export DEFAULT_VOICE="${DEFAULT_VOICE}"
export PODCAST_TITLE="${PODCAST_TITLE}"
export PODCAST_DESCRIPTION="${PODCAST_DESCRIPTION}"

cd /app

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Iniciando actualización programada..." >> /tmp/podcast_update.log

timeout 600 python3 articles_to_mp3.py \
    --config "$CONFIG_FILE" \
    --output "$AUDIO_DIR" \
    --tts "$TTS_ENGINE" \
    --voice "$DEFAULT_VOICE" \
    --generate-feed \
    --base-url "$BASE_URL" \
    --feed-title "$PODCAST_TITLE" \
    --feed-description "$PODCAST_DESCRIPTION" \
    >> /tmp/podcast_update.log 2>&1

if [ $? -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✓ Actualización completada" >> /tmp/podcast_update.log
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✗ Error en actualización" >> /tmp/podcast_update.log
fi
EOFSCRIPT

    chmod +x /tmp/update_script.sh

    # Exportar variables para el script de cron
    cat > /tmp/crontab << EOF
# Variables de entorno
CONFIG_FILE=$CONFIG_FILE
AUDIO_DIR=$AUDIO_DIR
BASE_URL=$BASE_URL
TTS_ENGINE=$TTS_ENGINE
DEFAULT_VOICE=$DEFAULT_VOICE
PODCAST_TITLE=${PODCAST_TITLE:-Mis Artículos TTS}
PODCAST_DESCRIPTION=${PODCAST_DESCRIPTION:-Artículos convertidos a audio}

# Crontab para supercronic
$CRON_SCHEDULE /tmp/update_script.sh
EOF

    log "${GREEN}✓ Crontab configurado${NC}"
    if [ "$DEBUG" = "1" ]; then
        log "${BLUE}Contenido del crontab:${NC}"
        cat /tmp/crontab
    fi
}

# Procesar comando
case "$1" in
    server)
        log "${GREEN}Modo: Servidor HTTP con actualizaciones automáticas${NC}"
        setup_cron

        # Iniciar supercronic en background
        supercronic /tmp/crontab >> /tmp/cron.log 2>&1 &
        CRON_PID=$!
        log "${GREEN}✓ Supercronic iniciado (PID: $CRON_PID)${NC}"

        # Actualización inicial
        if update_podcast; then
            log "${GREEN}✓ Actualización inicial exitosa${NC}"
        else
            log "${YELLOW}⚠️  Actualización inicial falló, pero continuando...${NC}"
        fi

        # Iniciar servidor (foreground)
        start_server
        ;;

    update)
        log "${GREEN}Modo: Actualización única${NC}"
        update_podcast
        ;;

    update-loop)
        log "${GREEN}Modo: Actualización continua sin servidor${NC}"
        setup_cron
        update_podcast

        # Ejecutar supercronic en foreground (mantiene el contenedor vivo)
        log "${GREEN}✓ Iniciando supercronic en foreground...${NC}"
        exec supercronic /tmp/crontab
        ;;

    test)
        log "${GREEN}Modo: Test de conectividad y configuración${NC}"
        check_network

        # Test de APIs
        log "${YELLOW}Probando acceso a APIs configuradas...${NC}"
        python3 << 'EOFPYTHON'
import json
import sys

try:
    with open('/data/config/config.json') as f:
        config = json.load(f)

    # Test Wallabag
    if 'wallabag' in config:
        print("✓ Configuración de Wallabag encontrada")
        print(f"  URL: {config['wallabag'].get('url', 'N/A')}")

    # Test FreshRSS
    if 'freshrss' in config:
        print("✓ Configuración de FreshRSS encontrada")
        print(f"  URL: {config['freshrss'].get('url', 'N/A')}")

except Exception as e:
    print(f"✗ Error leyendo config: {e}")
    sys.exit(1)
EOFPYTHON

        log "${GREEN}✓ Test completado${NC}"
        ;;

    bash)
        log "${GREEN}Modo: Shell interactivo${NC}"
        exec /bin/bash
        ;;

    *)
        echo -e "${RED}Uso: $0 {server|update|update-loop|test|bash}${NC}"
        echo -e "${YELLOW}  server      - Servidor HTTP + actualizaciones automáticas (predeterminado)${NC}"
        echo -e "${YELLOW}  update      - Actualización única y salir${NC}"
        echo -e "${YELLOW}  update-loop - Solo actualizaciones automáticas sin servidor${NC}"
        echo -e "${YELLOW}  test        - Test de conectividad y configuración${NC}"
        echo -e "${YELLOW}  bash        - Shell interactivo${NC}"
        exit 1
        ;;
esac
