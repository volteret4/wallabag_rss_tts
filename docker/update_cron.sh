#!/bin/bash
# Script de automatización para actualizar el podcast TTS diariamente
# Guarda este archivo como update_podcast.sh y hazlo ejecutable: chmod +x update_podcast.sh

# Configuración
SCRIPT_DIR="/ruta/a/tu/script"
TAILSCALE_IP="100.x.x.x"  # Cambia por tu IP de Tailscale
PORT="8005"
LOG_FILE="/var/log/podcast_tts.log"

# Función de log
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Ir al directorio del script
cd "$SCRIPT_DIR" || exit 1

log "=== Inicio de actualización del podcast ==="

# Activar entorno virtual si existe
if [ -d "venv" ]; then
    log "Activando entorno virtual..."
    source venv/bin/activate
fi

# Generar MP3s y feed RSS
log "Generando MP3s y actualizando feed RSS..."
python3 articles_to_mp3.py \
    --generate-feed \
    --base-url "http://${TAILSCALE_IP}:${PORT}" \
    2>&1 | tee -a "$LOG_FILE"

# Verificar si el servidor está corriendo
if ! pgrep -f "podcast_server.py" > /dev/null; then
    log "⚠️  El servidor no está corriendo. Considera usar systemd."
fi

# Obtener estadísticas
MP3_COUNT=$(find audio_articles -name "*.mp3" | wc -l)
log "✓ Actualización completada. Total de MP3s: $MP3_COUNT"

# Limpiar archivos antiguos (opcional, más de 30 días)
# log "Limpiando archivos antiguos..."
# find audio_articles -name "*.mp3" -mtime +30 -delete

log "=== Fin de actualización del podcast ==="
echo "" >> "$LOG_FILE"
