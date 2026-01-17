# Makefile para gestión del contenedor de Podcast TTS

.PHONY: help build up down restart logs shell update clean backup restore

# Configuración
IMAGE_NAME = podcast-tts
CONTAINER_NAME = podcast-tts
BACKUP_DIR = backups

help: ## Muestra esta ayuda
	@echo "Comandos disponibles:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ========== COMANDOS BÁSICOS ==========

build: ## Construye la imagen Docker
	docker compose build

up: ## Inicia el contenedor
	docker compose up -d
	@echo "✓ Contenedor iniciado"
	@echo "  Feed RSS: http://localhost:8005/podcast.xml"

down: ## Detiene el contenedor
	docker compose down

restart: ## Reinicia el contenedor
	docker compose restart
	@echo "✓ Contenedor reiniciado"

# ========== LOGS Y MONITOREO ==========

logs: ## Muestra logs en tiempo real
	docker compose logs -f

logs-tail: ## Muestra últimas 100 líneas de logs
	docker compose logs --tail=100

logs-update: ## Muestra logs de actualización
	docker compose exec $(CONTAINER_NAME) cat /tmp/podcast_update.log

logs-cron: ## Muestra logs de cron
	docker compose exec $(CONTAINER_NAME) cat /tmp/cron.log || echo "No hay logs de cron"

logs-all: ## Muestra todos los logs disponibles
	@echo "=== LOGS DEL CONTENEDOR ==="
	docker compose logs --tail=50
	@echo ""
	@echo "=== LOGS DE ACTUALIZACIÓN ==="
	docker compose exec $(CONTAINER_NAME) cat /tmp/podcast_update.log 2>/dev/null || echo "No disponible"
	@echo ""
	@echo "=== LOGS DE CRON ==="
	docker compose exec $(CONTAINER_NAME) cat /tmp/cron.log 2>/dev/null || echo "No disponible"

# ========== DIAGNÓSTICO ==========

diagnose: ## Ejecuta diagnóstico completo
	@chmod +x diagnostico.sh
	./diagnostico.sh

test: ## Ejecuta test de conectividad
	docker compose exec $(CONTAINER_NAME) /app/docker-entrypoint.sh test

test-dns: ## Test de DNS
	@echo "Probando DNS desde el contenedor..."
	docker compose exec $(CONTAINER_NAME) nslookup google.com || echo "✗ DNS no funciona"

test-https: ## Test de conectividad HTTPS
	@echo "Probando HTTPS desde el contenedor..."
	docker compose exec $(CONTAINER_NAME) curl -s --connect-timeout 5 https://www.google.com > /dev/null && echo "✓ HTTPS funciona" || echo "✗ HTTPS no funciona"

test-edge: ## Test de edge-tts
	@echo "Probando edge-tts..."
	docker compose exec $(CONTAINER_NAME) python3 -c "import edge_tts; print('✓ edge-tts instalado')" 2>/dev/null || echo "✗ edge-tts no funciona"
	@echo "Probando conectividad con Microsoft TTS..."
	docker compose exec $(CONTAINER_NAME) timeout 10 python3 -c "import asyncio; import edge_tts; asyncio.run(edge_tts.list_voices())" > /dev/null 2>&1 && echo "✓ Microsoft TTS accesible" || echo "✗ No se puede conectar a Microsoft TTS"

test-feed: ## Prueba que el feed RSS sea accesible
	@echo "Probando acceso al feed..."
	@curl -f http://localhost:8005/podcast.xml > /dev/null 2>&1 && echo "✓ Feed accesible" || echo "✗ Feed NO accesible"

check-config: ## Verifica la configuración
	@echo "=== Verificando Configuración ==="
	@if [ -f config.json ]; then \
		echo "✓ config.json existe" ; \
		python3 -m json.tool config.json > /dev/null && echo "✓ config.json es JSON válido" || echo "✗ config.json NO es JSON válido" ; \
	else \
		echo "✗ config.json NO existe" ; \
	fi
	@if [ -f docker-compose.yml ]; then \
		echo "✓ docker-compose.yml existe" ; \
	else \
		echo "✗ docker-compose.yml NO existe" ; \
	fi
	@echo ""
	@echo "Configuración en docker-compose.yml:"
	@grep "BASE_URL" docker-compose.yml || echo "  BASE_URL no configurada"
	@grep "TTS_ENGINE" docker-compose.yml || echo "  TTS_ENGINE no configurada"
	@grep "CRON_SCHEDULE" docker-compose.yml || echo "  CRON_SCHEDULE no configurada"

# ========== SHELL Y ACCESO ==========

shell: ## Accede al shell del contenedor
	docker compose exec $(CONTAINER_NAME) bash

shell-root: ## Accede al shell como root
	docker compose exec -u root $(CONTAINER_NAME) bash

# ========== ACTUALIZACIÓN ==========

update: ## Actualiza el podcast manualmente
	docker compose exec $(CONTAINER_NAME) python3 articles_to_mp3.py --generate-feed --base-url http://localhost:8005
	@echo "✓ Actualización manual completada"

update-gtts: ## Actualiza usando gTTS (si edge falla)
	docker compose exec $(CONTAINER_NAME) python3 articles_to_mp3.py --tts gtts --generate-feed --base-url http://localhost:8005
	@echo "✓ Actualización con gTTS completada"

update-debug: ## Actualiza con output completo
	docker compose exec $(CONTAINER_NAME) python3 articles_to_mp3.py \
		--config /data/config/config.json \
		--output /data/audio_articles \
		--generate-feed \
		--base-url http://localhost:8005 \
		--tts gtts

freshrss-list: ## Lista categorías y feeds de FreshRSS
	docker compose exec $(CONTAINER_NAME) python3 articles_to_mp3.py --freshrss-list

list-voices: ## Lista voces disponibles para edge-tts
	docker compose exec $(CONTAINER_NAME) python3 articles_to_mp3.py --list-voices

# ========== INFORMACIÓN ==========

status: ## Muestra el estado del contenedor
	@docker compose ps
	@echo ""
	@echo "Health check:"
	@docker inspect $(CONTAINER_NAME) 2>/dev/null | grep -A 5 '"Health"' || echo "No health info"

stats: ## Muestra estadísticas de recursos
	docker stats $(CONTAINER_NAME) --no-stream

count-mp3: ## Cuenta archivos MP3 generados
	@echo "MP3s generados:"
	@find ./audio_articles -name "*.mp3" 2>/dev/null | wc -l

list-mp3: ## Lista todos los MP3s generados
	@find ./audio_articles -name "*.mp3" -exec ls -lh {} \; 2>/dev/null

show-feed: ## Muestra información del feed RSS
	@if [ -f ./audio_articles/podcast.xml ]; then \
		echo "✓ podcast.xml existe" ; \
		echo "  Tamaño: $$(ls -lh ./audio_articles/podcast.xml | awk '{print $$5}')" ; \
		echo "  Episodios: $$(grep -c '<item>' ./audio_articles/podcast.xml)" ; \
		echo "" ; \
		echo "Últimos 5 episodios:" ; \
		grep '<title>' ./audio_articles/podcast.xml | head -6 | tail -5 ; \
	else \
		echo "✗ podcast.xml NO existe" ; \
	fi

# ========== LIMPIEZA ==========

clean: ## Limpia contenedores e imágenes no usadas
	docker compose down -v
	docker system prune -f
	@echo "✓ Limpieza completada"

clean-mp3: ## Elimina todos los MP3s (mantiene config)
	@echo "⚠️  Esto eliminará todos los MP3s. ¿Continuar? [y/N]"
	@read -r response; \
	if [ "$$response" = "y" ]; then \
		rm -f ./audio_articles/*.mp3 ./audio_articles/*.xml ; \
		echo "✓ MP3s eliminados" ; \
	else \
		echo "Cancelado" ; \
	fi

clean-all: ## Limpieza profunda (incluye archivos MP3)
	@echo "⚠️  Esto eliminará TODO. ¿Continuar? [y/N]"
	@read -r response; \
	if [ "$$response" = "y" ]; then \
		docker compose down -v ; \
		rm -rf audio_articles/*.mp3 audio_articles/*.xml ; \
		docker system prune -af ; \
		echo "✓ Limpieza profunda completada" ; \
	else \
		echo "Cancelado" ; \
	fi

# ========== BACKUP Y RESTORE ==========

backup: ## Crea backup de configuración y MP3s
	@mkdir -p $(BACKUP_DIR)
	@BACKUP_FILE=$(BACKUP_DIR)/podcast-backup-$$(date +%Y%m%d-%H%M%S).tar.gz ; \
	tar -czf $$BACKUP_FILE config.json docker-compose.yml audio_articles/ ; \
	echo "✓ Backup creado: $$BACKUP_FILE"

restore: ## Restaura desde el backup más reciente
	@LATEST_BACKUP=$$(ls -t $(BACKUP_DIR)/podcast-backup-*.tar.gz 2>/dev/null | head -1) ; \
	if [ -z "$$LATEST_BACKUP" ]; then \
		echo "✗ No se encontraron backups" ; \
		exit 1 ; \
	fi ; \
	echo "Restaurando desde: $$LATEST_BACKUP" ; \
	tar -xzf $$LATEST_BACKUP ; \
	echo "✓ Restauración completada"

list-backups: ## Lista todos los backups
	@ls -lh $(BACKUP_DIR)/podcast-backup-*.tar.gz 2>/dev/null || echo "No hay backups"

# ========== INSTALACIÓN Y SETUP ==========

install: ## Setup inicial completo
	@echo "=== Setup Inicial ==="
	@if [ ! -f config.json ]; then \
		echo "Copiando config_EXAMPLE.json a config.json..." ; \
		cp config_EXAMPLE.json config.json ; \
		echo "⚠️  Edita config.json con tus credenciales" ; \
	else \
		echo "✓ config.json ya existe" ; \
	fi
	@mkdir -p audio_articles
	@echo "Construyendo imagen..."
	@make build
	@echo ""
	@echo "=== Próximos pasos ==="
	@echo "1. Edita config.json con tus credenciales"
	@echo "2. Edita docker-compose.yml (BASE_URL con tu IP)"
	@echo "3. Ejecuta: make up"
	@echo "4. Verifica: make diagnose"

install-fixed: ## Instala usando archivos corregidos
	@echo "=== Instalación con Archivos Corregidos ==="
	@if [ -f Dockerfile-fixed ]; then cp Dockerfile-fixed Dockerfile; echo "✓ Dockerfile actualizado"; fi
	@if [ -f docker-compose-fixed.yml ]; then cp docker-compose-fixed.yml docker-compose.yml; echo "✓ docker-compose.yml actualizado"; fi
	@if [ -f docker-entrypoint-fixed.sh ]; then cp docker-entrypoint-fixed.sh docker-entrypoint.sh; chmod +x docker-entrypoint.sh; echo "✓ docker-entrypoint.sh actualizado"; fi
	@make install

update-build: ## Reconstruye la imagen y reinicia
	docker compose down
	docker compose build --no-cache
	docker compose up -d
	@echo "✓ Imagen actualizada y contenedor reiniciado"

# ========== TROUBLESHOOTING ==========

fix-permissions: ## Corrige permisos del directorio audio
	@echo "Corrigiendo permisos..."
	@sudo chown -R 1000:1000 ./audio_articles
	@echo "✓ Permisos corregidos"

recreate: ## Recrea el contenedor desde cero
	docker compose down -v
	docker compose build --no-cache
	docker compose up -d
	@echo "✓ Contenedor recreado"

reset: ## Reset completo (mantiene config.json)
	@echo "⚠️  Esto eliminará el contenedor, volúmenes y MP3s. ¿Continuar? [y/N]"
	@read -r response; \
	if [ "$$response" = "y" ]; then \
		docker compose down -v ; \
		rm -f ./audio_articles/*.mp3 ./audio_articles/*.xml ; \
		docker compose build --no-cache ; \
		docker compose up -d ; \
		echo "✓ Reset completado" ; \
	else \
		echo "Cancelado" ; \
	fi

# ========== UTILIDADES ==========

tailscale-ip: ## Muestra tu IP de Tailscale
	@echo "Tu IP de Tailscale:"
	@tailscale ip -4 2>/dev/null || echo "Tailscale no está instalado o no está corriendo"

watch-logs: ## Observa logs en tiempo real con filtrado
	docker compose logs -f | grep -E "(✓|✗|ERROR|WARNING|Generando|Obtenidos)"

quick-check: ## Verificación rápida del sistema
	@echo "=== Verificación Rápida ==="
	@echo -n "Contenedor: "; docker ps | grep -q podcast-tts && echo "✓ Corriendo" || echo "✗ Detenido"
	@echo -n "Config: "; [ -f config.json ] && echo "✓ Existe" || echo "✗ No existe"
	@echo -n "MP3s: "; find ./audio_articles -name "*.mp3" 2>/dev/null | wc -l
	@echo -n "Feed: "; [ -f ./audio_articles/podcast.xml ] && echo "✓ Existe" || echo "✗ No existe"
	@echo -n "Feed accesible: "; curl -f -s http://localhost:8005/podcast.xml > /dev/null 2>&1 && echo "✓ Sí" || echo "✗ No"
