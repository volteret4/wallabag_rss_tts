#!/bin/bash
# Script de inicio rápido para el sistema de Podcast TTS con Docker

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║    Sistema de Podcast TTS - Setup Rápido         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
echo ""

# Función para verificar si un comando existe
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Verificar Docker
echo -e "${YELLOW}[1/6] Verificando dependencias...${NC}"
if ! command_exists docker; then
    echo -e "${RED}✗ Docker no está instalado${NC}"
    echo -e "${YELLOW}  Instala Docker desde: https://docs.docker.com/get-docker/${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker instalado${NC}"

# Verificar Docker Compose
if ! command_exists docker compose version 2>/dev/null; then
    echo -e "${RED}✗ Docker Compose no está instalado${NC}"
    echo -e "${YELLOW}  Instala Docker Compose desde: https://docs.docker.com/compose/install/${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose instalado${NC}"

# Crear config.json si no existe
echo ""
echo -e "${YELLOW}[2/6] Configurando archivos...${NC}"
if [ ! -f config.json ]; then
    if [ -f config.json.example_v3 ]; then
        cp config.json.example_v3 config.json
        echo -e "${GREEN}✓ config.json creado desde ejemplo${NC}"
        echo -e "${YELLOW}  ⚠️  IMPORTANTE: Edita config.json con tus credenciales${NC}"

        # Preguntar si quiere editar ahora
        read -p "¿Quieres editar config.json ahora? (s/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Ss]$ ]]; then
            ${EDITOR:-nano} config.json
        fi
    else
        echo -e "${RED}✗ No se encuentra config.json.example_v3${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ config.json ya existe${NC}"
fi

# Verificar/obtener IP de Tailscale
echo ""
echo -e "${YELLOW}[3/6] Configurando red...${NC}"
if command_exists tailscale; then
    TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "")
    if [ -n "$TAILSCALE_IP" ]; then
        echo -e "${GREEN}✓ Tailscale detectado${NC}"
        echo -e "${GREEN}  Tu IP de Tailscale: $TAILSCALE_IP${NC}"

        # Actualizar docker-compose.yml con la IP
        if [ -f docker-compose.yml ]; then
            # Backup
            cp docker-compose.yml docker-compose.yml.bak

            # Reemplazar IP en BASE_URL
            sed -i "s|BASE_URL=http://[0-9.]*:[0-9]*|BASE_URL=http://$TAILSCALE_IP:8005|g" docker-compose.yml
            echo -e "${GREEN}✓ docker-compose.yml actualizado con tu IP de Tailscale${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  Tailscale instalado pero no está corriendo${NC}"
        echo -e "${YELLOW}  Ejecuta: sudo tailscale up${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Tailscale no está instalado${NC}"
    echo -e "${YELLOW}  Se usará localhost. Para acceso remoto, instala Tailscale:${NC}"
    echo -e "${YELLOW}  https://tailscale.com/download${NC}"
fi

# Crear directorio de audio
echo ""
echo -e "${YELLOW}[4/6] Creando directorios...${NC}"
mkdir -p audio_articles
echo -e "${GREEN}✓ Directorio audio_articles creado${NC}"

# Construir imagen
echo ""
echo -e "${YELLOW}[5/6] Construyendo imagen Docker...${NC}"
echo -e "${BLUE}  Esto puede tardar unos minutos la primera vez...${NC}"
docker compose build

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Imagen construida exitosamente${NC}"
else
    echo -e "${RED}✗ Error al construir la imagen${NC}"
    exit 1
fi

# Iniciar contenedor
echo ""
echo -e "${YELLOW}[6/6] Iniciando contenedor...${NC}"
docker compose up -d

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Contenedor iniciado${NC}"
else
    echo -e "${RED}✗ Error al iniciar el contenedor${NC}"
    exit 1
fi

# Esperar a que el contenedor esté listo
echo -e "${BLUE}  Esperando que el servicio esté listo...${NC}"
sleep 5

# Mostrar información final
echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              ¡Setup Completado! 🎉                ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}📡 URLs de acceso:${NC}"
echo -e "   Local:     ${GREEN}http://localhost:8005/podcast.xml${NC}"
if [ -n "$TAILSCALE_IP" ]; then
    echo -e "   Tailscale: ${GREEN}http://$TAILSCALE_IP:8005/podcast.xml${NC}"
fi
echo ""
echo -e "${BLUE}🎯 Próximos pasos:${NC}"
echo -e "   1. Verifica los logs: ${YELLOW}docker compose logs -f${NC}"
echo -e "   2. Espera a que se generen los MP3s"
echo -e "   3. Añade el feed a AntennaPod"
if [ -n "$TAILSCALE_IP" ]; then
    echo -e "      URL: ${GREEN}http://$TAILSCALE_IP:8005/podcast.xml${NC}"
else
    echo -e "      URL: ${GREEN}http://localhost:8005/podcast.xml${NC}"
fi
echo ""
echo -e "${BLUE}📚 Comandos útiles:${NC}"
echo -e "   Ver logs:        ${YELLOW}docker compose logs -f${NC}"
echo -e "   Detener:         ${YELLOW}docker compose down${NC}"
echo -e "   Reiniciar:       ${YELLOW}docker compose restart${NC}"
echo -e "   Actualizar MP3s: ${YELLOW}docker compose exec podcast-tts python3 articles_to_mp3.py --generate-feed${NC}"
echo -e "   Shell:           ${YELLOW}docker compose exec podcast-tts bash${NC}"
echo ""
echo -e "${BLUE}📖 Más información:${NC}"
echo -e "   README_DOCKER.md"
echo ""

# Preguntar si quiere ver los logs
read -p "¿Quieres ver los logs ahora? (s/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Ss]$ ]]; then
    echo ""
    echo -e "${BLUE}Presiona Ctrl+C para salir de los logs${NC}"
    sleep 2
    docker compose logs -f
fi
