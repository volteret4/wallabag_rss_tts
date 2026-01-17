#!/bin/bash
#
# generate-podcast-feed.sh
# Genera un feed RSS/Podcast a partir de archivos MP3 en un directorio
#
# Uso:
#   ./generate-podcast-feed.sh [OPTIONS]
#
# Opciones:
#   -d, --dir <directorio>       Directorio con los archivos MP3 (default: ./audio_articles)
#   -u, --url <url>              URL base del podcast (default: http://localhost:8005)
#   -t, --title <título>         Título del podcast (default: Mi Podcast TTS)
#   -D, --description <desc>     Descripción del podcast
#   -o, --output <archivo>       Archivo de salida (default: podcast.xml)
#   -l, --language <idioma>      Idioma del podcast (default: es)
#   -a, --author <autor>         Autor del podcast
#   -e, --email <email>          Email del autor
#   -i, --image <url>            URL de la imagen del podcast
#   -m, --max <número>           Máximo número de episodios (default: todos)
#   -h, --help                   Mostrar esta ayuda
#

set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuración por defecto
AUDIO_DIR="./audio_articles"
BASE_URL="http://localhost:8005"
PODCAST_TITLE="Mi Podcast TTS"
PODCAST_DESCRIPTION="Artículos convertidos a audio mediante Text-to-Speech"
OUTPUT_FILE="podcast.xml"
LANGUAGE="es"
AUTHOR=""
EMAIL=""
IMAGE_URL=""
MAX_EPISODES=""

# Funciones de ayuda
error() {
    echo -e "${RED}✗ Error: $1${NC}" >&2
    exit 1
}

success() {
    echo -e "${GREEN}✓ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

info() {
    echo -e "${BLUE}→ $1${NC}"
}

show_help() {
    head -n 20 "$0" | grep "^#" | sed 's/^# \?//'
    exit 0
}

# Función para obtener duración del MP3
get_mp3_duration() {
    local file="$1"
    local duration=0

    # Intentar con ffprobe (más preciso)
    if command -v ffprobe &> /dev/null; then
        duration=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$file" 2>/dev/null | cut -d. -f1)
    # Intentar con mp3info
    elif command -v mp3info &> /dev/null; then
        duration=$(mp3info -p "%S" "$file" 2>/dev/null)
    # Intentar con soxi (sox)
    elif command -v soxi &> /dev/null; then
        duration=$(soxi -D "$file" 2>/dev/null | cut -d. -f1)
    # Estimación basada en tamaño (bitrate promedio 128kbps = 16KB/s)
    else
        local size=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null)
        if [ -n "$size" ]; then
            duration=$((size / 16000))
        fi
    fi

    echo "${duration:-0}"
}

# Función para formatear duración en HH:MM:SS
format_duration() {
    local total_seconds=$1
    local hours=$((total_seconds / 3600))
    local minutes=$(( (total_seconds % 3600) / 60 ))
    local seconds=$((total_seconds % 60))
    printf "%02d:%02d:%02d" $hours $minutes $seconds
}

# Función para escapar XML
xml_escape() {
    echo "$1" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/"/\&quot;/g; s/'"'"'/\&apos;/g'
}

# Función para obtener RFC 2822 date
get_rfc2822_date() {
    local file="$1"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        date -r "$(stat -f %m "$file")" "+%a, %d %b %Y %H:%M:%S %z"
    else
        # Linux
        date -d "@$(stat -c %Y "$file")" "+%a, %d %b %Y %H:%M:%S %z"
    fi
}

# Parsear argumentos
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--dir)
            AUDIO_DIR="$2"
            shift 2
            ;;
        -u|--url)
            BASE_URL="$2"
            shift 2
            ;;
        -t|--title)
            PODCAST_TITLE="$2"
            shift 2
            ;;
        -D|--description)
            PODCAST_DESCRIPTION="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -l|--language)
            LANGUAGE="$2"
            shift 2
            ;;
        -a|--author)
            AUTHOR="$2"
            shift 2
            ;;
        -e|--email)
            EMAIL="$2"
            shift 2
            ;;
        -i|--image)
            IMAGE_URL="$2"
            shift 2
            ;;
        -m|--max)
            MAX_EPISODES="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            ;;
        *)
            error "Opción desconocida: $1\nUsa --help para ver las opciones disponibles"
            ;;
    esac
done

# Validaciones
if [ ! -d "$AUDIO_DIR" ]; then
    error "El directorio no existe: $AUDIO_DIR"
fi

# Remover trailing slash de URLs
BASE_URL="${BASE_URL%/}"

# Información inicial
echo ""
info "=== Generador de Feed RSS para Podcast ==="
echo ""
info "Directorio: $AUDIO_DIR"
info "URL base: $BASE_URL"
info "Título: $PODCAST_TITLE"
info "Salida: $OUTPUT_FILE"
echo ""

# Buscar archivos MP3
mapfile -t mp3_files < <(find "$AUDIO_DIR" -maxdepth 1 -type f \( -iname "*.mp3" -o -iname "*.m4a" \) | sort -r)

if [ ${#mp3_files[@]} -eq 0 ]; then
    error "No se encontraron archivos MP3 en $AUDIO_DIR"
fi

info "Archivos encontrados: ${#mp3_files[@]}"

# Limitar número de episodios si se especificó
if [ -n "$MAX_EPISODES" ] && [ "$MAX_EPISODES" -gt 0 ]; then
    mp3_files=("${mp3_files[@]:0:$MAX_EPISODES}")
    info "Limitando a: $MAX_EPISODES episodios"
fi

# Generar XML header
cat > "$OUTPUT_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>$(xml_escape "$PODCAST_TITLE")</title>
    <description>$(xml_escape "$PODCAST_DESCRIPTION")</description>
    <link>$BASE_URL</link>
    <language>$LANGUAGE</language>
    <lastBuildDate>$(date "+%a, %d %b %Y %H:%M:%S %z")</lastBuildDate>
    <generator>generate-podcast-feed.sh</generator>
EOF

# Añadir autor si se especificó
if [ -n "$AUTHOR" ]; then
    echo "    <itunes:author>$(xml_escape "$AUTHOR")</itunes:author>" >> "$OUTPUT_FILE"
fi

# Añadir email si se especificó
if [ -n "$EMAIL" ]; then
    if [ -n "$AUTHOR" ]; then
        echo "    <managingEditor>$EMAIL ($(xml_escape "$AUTHOR"))</managingEditor>" >> "$OUTPUT_FILE"
    else
        echo "    <managingEditor>$EMAIL</managingEditor>" >> "$OUTPUT_FILE"
    fi
fi

# Añadir imagen si se especificó
if [ -n "$IMAGE_URL" ]; then
    cat >> "$OUTPUT_FILE" << EOF
    <itunes:image href="$IMAGE_URL"/>
    <image>
      <url>$IMAGE_URL</url>
      <title>$(xml_escape "$PODCAST_TITLE")</title>
      <link>$BASE_URL</link>
    </image>
EOF
fi

echo "" >> "$OUTPUT_FILE"

# Procesar cada archivo MP3
episode_count=0
for mp3_file in "${mp3_files[@]}"; do
    ((episode_count++))

    filename=$(basename "$mp3_file")
    title="${filename%.*}"  # Remover extensión

    # Limpiar el título
    # Remover prefijos como [Categoría] si existen
    title=$(echo "$title" | sed 's/^\[[^]]*\] //')
    # Remover timestamps si existen
    title=$(echo "$title" | sed 's/_[0-9]\{8\}_[0-9]\{6\}$//')

    info "Procesando: $title"

    # Obtener metadatos
    file_size=$(stat -f%z "$mp3_file" 2>/dev/null || stat -c%s "$mp3_file" 2>/dev/null)
    pub_date=$(get_rfc2822_date "$mp3_file")
    duration=$(get_mp3_duration "$mp3_file")
    duration_formatted=$(format_duration "$duration")

    # URL del archivo
    file_url="$BASE_URL/$filename"

    # Generar GUID único (basado en nombre de archivo)
    guid=$(echo -n "$file_url" | md5sum 2>/dev/null | cut -d' ' -f1 || echo "$file_url")

    # Añadir item al feed
    cat >> "$OUTPUT_FILE" << EOF
    <item>
      <title>$(xml_escape "$title")</title>
      <description>$(xml_escape "$title")</description>
      <pubDate>$pub_date</pubDate>
      <enclosure url="$file_url" length="$file_size" type="audio/mpeg"/>
      <guid isPermaLink="false">$guid</guid>
      <itunes:duration>$duration_formatted</itunes:duration>
      <itunes:explicit>no</itunes:explicit>
    </item>

EOF
done

# Cerrar XML
cat >> "$OUTPUT_FILE" << EOF
  </channel>
</rss>
EOF

# Formatear XML (si xmllint está disponible)
if command -v xmllint &> /dev/null; then
    info "Formateando XML..."
    xmllint --format "$OUTPUT_FILE" -o "$OUTPUT_FILE.tmp" 2>/dev/null && mv "$OUTPUT_FILE.tmp" "$OUTPUT_FILE"
fi

# Resumen
echo ""
success "Feed RSS generado exitosamente"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📄 Archivo: $OUTPUT_FILE"
echo "📊 Episodios: $episode_count"
echo "🔗 URL del feed: $BASE_URL/$(basename "$OUTPUT_FILE")"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Validar XML
if command -v xmllint &> /dev/null; then
    if xmllint --noout "$OUTPUT_FILE" 2>/dev/null; then
        success "XML válido ✓"
    else
        warning "El XML podría tener errores. Ejecuta: xmllint --noout $OUTPUT_FILE"
    fi
fi

echo ""
info "Para usar en AntennaPod:"
echo "  1. Añadir podcast por URL"
echo "  2. Introducir: $BASE_URL/$(basename "$OUTPUT_FILE")"
echo ""

# Mostrar primeros episodios
if [ $episode_count -gt 0 ]; then
    info "Últimos 3 episodios agregados:"
    head -n 3 <<< "${mp3_files[@]}" | while read -r file; do
        if [ -n "$file" ]; then
            echo "  • $(basename "$file" .mp3)"
        fi
    done
    echo ""
fi

success "¡Listo! 🎉"
echo ""
