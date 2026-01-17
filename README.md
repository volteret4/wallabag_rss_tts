# Sistema de Podcast TTS - Docker 🐳

Sistema completo de podcast personal usando Docker. Convierte artículos de FreshRSS y Wallabag a MP3 y genera un feed RSS accesible desde AntennaPod.

## 🚀 Inicio Rápido (5 minutos)

```bash
# 1. Clonar o descargar los archivos
cd podcast-tts

# 2. Crear configuración
cp config.json.example_v3 config.json
nano config.json  # Editar con tus credenciales

# 3. Obtener tu IP de Tailscale
tailscale ip -4

# 4. Editar docker-compose.yml
nano docker-compose.yml
# Cambiar BASE_URL=http://TU-IP-TAILSCALE:8000

# 5. Iniciar el contenedor
docker compose up -d

# 6. Ver logs
docker compose logs -f

# 7. Añadir a AntennaPod
# URL: http://TU-IP-TAILSCALE:8000/podcast.xml
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
  - BASE_URL=http://100.x.x.x:8000 # ← Tu IP de Tailscale
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

- Inicia servidor HTTP en puerto 8000
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

- **Feed RSS**: `http://TU-IP-TAILSCALE:8000/podcast.xml`
- **Navegador**: `http://TU-IP-TAILSCALE:8000/`
- **Local**: `http://localhost:8000/podcast.xml`

### Añadir a AntennaPod

1. Abre AntennaPod
2. **"+"** → **"Añadir podcast por URL"**
3. Pega: `http://TU-IP-TAILSCALE:8000/podcast.xml`
4. **"Confirmar"**

## 🔧 Variables de Entorno

Todas configurables en `docker-compose.yml`:

| Variable              | Descripción           | Predeterminado                  |
| --------------------- | --------------------- | ------------------------------- |
| `BASE_URL`            | URL base del feed     | `http://localhost:8000`         |
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

**Importante**: Los archivos persisten en el host, no se pierden al reiniciar el contenedor.

## 🔄 Actualización del Sistema

### Actualizar la imagen

```bash
# Detener contenedor
docker compose down

# Reconstruir imagen
docker compose build --no-cache

# Iniciar nuevamente
docker compose up -d
```

### Actualizar configuración

```bash
# Editar config.json
nano config.json

# Reiniciar para aplicar cambios
docker compose restart
```

## 📊 Logs y Monitorización

### Ver logs

```bash
# Todos los logs
docker compose logs -f

# Solo últimas 100 líneas
docker compose logs --tail=100

# Logs de actualización
docker compose exec podcast-tts tail -f /var/log/podcast_update.log
```

### Health Check

El contenedor incluye health check automático:

```bash
# Ver estado de salud
docker compose ps

# Ver detalles del health check
docker inspect podcast-tts | grep -A 10 Health
```

### Estadísticas

```bash
# Uso de recursos
docker stats podcast-tts

# Número de MP3s generados
docker compose exec podcast-tts find /data/audio_articles -name "*.mp3" | wc -l
```

## 🛠️ Troubleshooting

### El contenedor no inicia

```bash
# Ver logs de error
docker compose logs

# Verificar config.json
docker compose run --rm podcast-tts cat /data/config/config.json

# Probar shell interactivo
docker compose run --rm podcast-tts bash
```

### No genera MP3s

```bash
# Ejecutar actualización manualmente
docker compose exec podcast-tts python3 articles_to_mp3_v3.py \
  --config /data/config/config.json \
  --output /data/audio_articles \
  --generate-feed \
  --freshrss-list

# Ver logs de cron
docker compose exec podcast-tts tail -f /var/log/podcast_update.log
```

### No puedo acceder al feed desde AntennaPod

```bash
# Verificar que el servidor está corriendo
curl http://localhost:8000/podcast.xml

# Verificar puerto expuesto
docker compose port podcast-tts 8000

# Verificar Tailscale
tailscale status
curl http://$(tailscale ip -4):8000/podcast.xml
```

### Puerto 8000 en uso

Cambiar puerto en `docker-compose.yml`:

```yaml
ports:
  - "9000:8000" # Host:Container

environment:
  - BASE_URL=http://100.x.x.x:9000 # ← Cambiar también aquí
```

## 🔐 Seguridad

### Buenas prácticas

1. **No expongas el puerto a internet público**

   ```yaml
   ports:
     - "127.0.0.1:8000:8000" # Solo localhost
   ```

2. **Usa Tailscale para acceso remoto seguro**
   - Conexión encriptada
   - Solo dispositivos autorizados

3. **Protege tu config.json**

   ```bash
   chmod 600 config.json
   ```

4. **Revisa logs regularmente**
   ```bash
   docker compose logs --since 24h
   ```

## 📦 Portabilidad

### Exportar configuración completa

```bash
# Crear backup
tar -czf podcast-backup.tar.gz \
  config.json \
  docker-compose.yml \
  audio_articles/

# Restaurar en otro servidor
tar -xzf podcast-backup.tar.gz
docker compose up -d
```

### Migrar a otro servidor

```bash
# En servidor original
docker compose down
tar -czf podcast-full.tar.gz .

# En servidor nuevo
tar -xzf podcast-full.tar.gz
docker compose up -d
```

## 🎯 Ejemplos de Uso

### Caso 1: Actualización cada 6 horas

```yaml
environment:
  - CRON_SCHEDULE=0 */6 * * *
```

### Caso 2: Solo días laborables

```yaml
environment:
  - CRON_SCHEDULE=0 7 * * 1-5 # Lunes a viernes
```

### Caso 3: Múltiples voces

```json
{
  "categories": [
    { "name": "Tech", "voice": "en-US-GuyNeural" },
    { "name": "Español", "voice": "es-ES-ElviraNeural" },
    { "name": "México", "voice": "es-MX-DaliaNeural" }
  ]
}
```

### Caso 4: Integración con Portainer

Compatible con Portainer para gestión visual.

### Caso 5: Múltiples instancias

```bash
# Crear segundo podcast
cp -r podcast-tts podcast-noticias
cd podcast-noticias

# Editar docker-compose.yml
# - Cambiar container_name
# - Cambiar puerto (8001)
# - Cambiar BASE_URL

docker compose up -d
```

## 🚀 Optimizaciones

### Reducir tamaño de imagen

La imagen ya usa multi-stage build y `python:slim`.

### Cachear dependencias

```dockerfile
# En Dockerfile
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Las dependencias se cachean aquí
```

### Limitar recursos

```yaml
services:
  podcast-tts:
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 512M
        reservations:
          memory: 256M
```

## 📚 Comandos útiles de Docker

```bash
# Ver imágenes
docker images

# Limpiar imágenes no usadas
docker image prune -a

# Ver espacio usado
docker system df

# Limpiar todo lo no usado
docker system prune -a

# Exportar imagen
docker save podcast-tts > podcast-tts.tar

# Importar imagen
docker load < podcast-tts.tar
```

## ✅ Checklist de Instalación

- [ ] Docker y Docker Compose instalados
- [ ] Tailscale configurado
- [ ] config.json creado y configurado
- [ ] docker-compose.yml editado con tu IP
- [ ] Contenedor iniciado: `docker compose up -d`
- [ ] Logs verificados: `docker compose logs -f`
- [ ] Feed accesible: `curl http://localhost:8000/podcast.xml`
- [ ] Feed añadido a AntennaPod
- [ ] Actualización automática funcionando

## 🎉 Ventajas de la Versión Docker

✅ **Setup en 5 minutos** - No hay que instalar dependencias  
✅ **Portable** - Mismo entorno en cualquier servidor  
✅ **Aislado** - No contamina el sistema host  
✅ **Auto-reinicio** - Si se cae, se reinicia solo  
✅ **Fácil actualización** - `docker compose pull && docker compose up -d`  
✅ **Logs centralizados** - `docker compose logs`  
✅ **Health checks** - Monitorización automática  
✅ **Backup simple** - Solo copiar el directorio

---

**¡Tu podcast personal está listo!** 🎙️

Para más información, consulta:

- README_v3.md - Documentación completa
- TROUBLESHOOTING_PODCAST.md - Solución de problemas
