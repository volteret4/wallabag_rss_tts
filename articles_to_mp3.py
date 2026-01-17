#!/usr/bin/env python3
"""
Script mejorado para convertir artículos de Wallabag y FreshRSS a MP3 usando TTS
Genera feed RSS para podcasts
Requiere: pip install gtts edge-tts requests feedparser beautifulsoup4 mutagen langdetect deep-translator --break-system-packages
"""

import os
import json
import requests
import feedparser
from gtts import gTTS
from bs4 import BeautifulSoup
from datetime import datetime
import re
import argparse
import asyncio
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom


class ArticleToMP3Converter:
    def __init__(self, output_dir="audio_articles", tts_engine="edge", voice="es-ES-AlvaroNeural",
                 skip_existing=True, target_language=None):
        self.output_dir = output_dir
        self.tts_engine = tts_engine
        self.voice = voice
        self.skip_existing = skip_existing
        self.target_language = target_language
        os.makedirs(output_dir, exist_ok=True)

    def detect_language(self, text):
        """Detecta el idioma del texto"""
        try:
            from langdetect import detect, LangDetectException
            # Usar solo los primeros 1000 caracteres para detección más rápida
            sample = text[:1000] if len(text) > 1000 else text
            detected = detect(sample)
            return detected
        except Exception as e:
            print(f"⚠ Error al detectar idioma: {e}")
            return None

    def translate_text(self, text, source_lang, target_lang):
        """Traduce el texto del idioma origen al idioma destino"""
        try:
            from deep_translator import GoogleTranslator

            print(f"🔄 Traduciendo de {source_lang} a {target_lang}...")

            # Límite de 4900 caracteres por consulta (margen de seguridad)
            max_length_per_chunk = 4900
            max_chunks = 4  # Hasta 4 consultas
            max_total_length = max_length_per_chunk * max_chunks  # 19600 caracteres máximo

            original_length = len(text)

            # Si el texto es muy largo, truncar
            if original_length > max_total_length:
                print(f"⚠ Texto muy largo ({original_length} caracteres), truncando a {max_total_length}...")
                text = text[:max_total_length]
                original_length = len(text)

            # Calcular número de chunks necesarios
            num_chunks = (original_length + max_length_per_chunk - 1) // max_length_per_chunk

            translator = GoogleTranslator(source=source_lang, target=target_lang)

            # Si cabe en una sola consulta
            if num_chunks == 1:
                print(f"📝 Traduciendo en 1 consulta ({original_length} caracteres)...")
                translated = translator.translate(text)
                print(f"✓ Traducción completada ({len(translated)} caracteres)")
                return translated

            # Si necesita múltiples consultas
            else:
                print(f"📝 Traduciendo en {num_chunks} consultas ({original_length} caracteres totales)...")

                chunks = []
                chunk_size = original_length // num_chunks

                # Dividir el texto en chunks
                for i in range(num_chunks):
                    if i == num_chunks - 1:
                        # Último chunk: tomar todo lo que queda
                        chunk_start = i * chunk_size
                        chunk = text[chunk_start:].strip()
                    else:
                        # Buscar punto de corte natural
                        chunk_start = i * chunk_size
                        chunk_end = (i + 1) * chunk_size

                        # Buscar un buen punto de corte (espacio, salto de línea o punto)
                        search_range = 100
                        best_cut = chunk_end

                        for j in range(max(chunk_start, chunk_end - search_range),
                                      min(len(text), chunk_end + search_range)):
                            if text[j] in ['\n', '.', '!', '?', ' ']:
                                if abs(j - chunk_end) < abs(best_cut - chunk_end):
                                    best_cut = j + 1

                        chunk = text[chunk_start:best_cut].strip()

                    chunks.append(chunk)

                # Traducir cada chunk
                translated_chunks = []
                for idx, chunk in enumerate(chunks, 1):
                    print(f"  Parte {idx}/{num_chunks}: {len(chunk)} caracteres...")
                    translated_chunk = translator.translate(chunk)
                    translated_chunks.append(translated_chunk)

                # Unir las traducciones con un espacio
                translated = " ".join(translated_chunks)

                print(f"✓ Traducción completada ({len(translated)} caracteres)")
                return translated

        except Exception as e:
            print(f"✗ Error al traducir: {e}")
            print("  Usando texto original sin traducir")
            return text

    def clean_text(self, text):
        """Limpia el texto HTML y lo prepara para TTS"""
        soup = BeautifulSoup(text, 'html.parser')

        # Eliminar scripts y estilos
        for script in soup(["script", "style"]):
            script.decompose()

        # Obtener texto
        text = soup.get_text()

        # Limpiar espacios en blanco
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)

        return text

    def sanitize_filename(self, filename):
        """Convierte un título en un nombre de archivo válido"""
        # Eliminar caracteres no válidos
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # Limitar longitud
        filename = filename[:100]
        return filename.strip()

    async def text_to_mp3_edge(self, text, filepath):
        """Convierte texto a MP3 usando edge-tts (Microsoft Edge TTS)"""
        try:
            import edge_tts

            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(filepath)
            return True
        except Exception as e:
            print(f"✗ Error con edge-tts: {e}")
            return False

    def text_to_mp3_gtts(self, text, filepath, lang='es'):
        """Convierte texto a MP3 usando gTTS (Google TTS)"""
        try:
            tts = gTTS(text=text, lang=lang, slow=False)
            tts.save(filepath)
            return True
        except Exception as e:
            print(f"✗ Error con gTTS: {e}")
            return False

    def process_and_convert(self, text, title, original_language=None, lang='es'):
        """
        Procesa el texto (detecta idioma, traduce si es necesario) y lo convierte a MP3

        Args:
            text: Texto a convertir
            title: Título del artículo
            original_language: Idioma original especificado en config (opcional)
            lang: Idioma para gTTS
        """
        # Detectar idioma si no se especificó
        if self.target_language:
            detected_lang = original_language or self.detect_language(text)

            if detected_lang:
                print(f"📝 Idioma detectado: {detected_lang}")

                # Normalizar códigos de idioma (en-us -> en, es-es -> es, etc.)
                detected_lang_short = detected_lang.split('-')[0].lower()
                target_lang_short = self.target_language.split('-')[0].lower()

                # Traducir si es necesario
                if detected_lang_short != target_lang_short:
                    print(f"🌐 Traducción necesaria: {detected_lang_short} → {target_lang_short}")
                    text = self.translate_text(text, detected_lang_short, target_lang_short)
                else:
                    print(f"✓ Sin traducción necesaria (ya está en {target_lang_short})")

        # Convertir a MP3
        return self.text_to_mp3(text, title, lang)

    def text_to_mp3(self, text, title, lang='es'):
        """Convierte texto a MP3 usando el motor TTS configurado"""
        try:
            filename = self.sanitize_filename(title)
            filepath = os.path.join(self.output_dir, f"{filename}.mp3")

            # Comprobar si el archivo ya existe
            if os.path.exists(filepath):
                if self.skip_existing:
                    print(f"⊙ Ya existe (omitiendo): {filename}.mp3")
                    return filepath
                else:
                    # Si no se quiere omitir, crear con timestamp
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filepath = os.path.join(self.output_dir, f"{filename}_{timestamp}.mp3")
                    print(f"⚠ Archivo existe, creando nueva versión: {filename}_{timestamp}.mp3")

            print(f"Generando audio ({self.tts_engine}): {filename}.mp3")

            success = False
            if self.tts_engine == "edge":
                # edge-tts es asíncrono, usar asyncio
                success = asyncio.run(self.text_to_mp3_edge(text, filepath))
            elif self.tts_engine == "gtts":
                success = self.text_to_mp3_gtts(text, filepath, lang)

            if success:
                print(f"✓ Guardado: {filepath}")
                return filepath
            else:
                print(f"✗ Error al generar audio para '{title}'")
                return None

        except Exception as e:
            print(f"✗ Error al generar audio para '{title}': {e}")
            return None


class WallabagClient:
    def __init__(self, url, client_id, client_secret, username, password):
        self.url = url.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.username = username
        self.password = password
        self.token = None

    def authenticate(self):
        """Obtiene el token de acceso de Wallabag"""
        auth_url = f"{self.url}/oauth/v2/token"
        data = {
            'grant_type': 'password',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'username': self.username,
            'password': self.password
        }

        try:
            response = requests.post(auth_url, data=data)
            response.raise_for_status()
            self.token = response.json()['access_token']
            print("✓ Autenticado en Wallabag")
            return True
        except Exception as e:
            print(f"✗ Error de autenticación en Wallabag: {e}")
            return False

    def get_articles(self, archive=0, limit=10):
        """Obtiene artículos de Wallabag"""
        if not self.token:
            if not self.authenticate():
                return []

        headers = {'Authorization': f'Bearer {self.token}'}
        params = {
            'archive': archive,
            'perPage': limit,
            'order': 'desc',
            'sort': 'created'
        }

        try:
            response = requests.get(
                f"{self.url}/api/entries.json",
                headers=headers,
                params=params
            )
            response.raise_for_status()
            articles = response.json()['_embedded']['items']
            print(f"✓ Obtenidos {len(articles)} artículos de Wallabag")
            return articles
        except Exception as e:
            print(f"✗ Error al obtener artículos de Wallabag: {e}")
            return []


class FreshRSSClient:
    def __init__(self, url, username, password):
        self.url = url.rstrip('/')
        self.username = username
        self.password = password
        self.auth_token = None

    def authenticate(self):
        """Autenticación usando Google Reader API de FreshRSS"""
        login_url = f"{self.url}/api/greader.php/accounts/ClientLogin"

        data = {
            'Email': self.username,
            'Passwd': self.password
        }

        try:
            response = requests.post(login_url, data=data)
            response.raise_for_status()

            for line in response.text.strip().split('\n'):
                if line.startswith('Auth='):
                    self.auth_token = line.split('=', 1)[1]
                    print(f"✓ Autenticado en FreshRSS")
                    return True

            print("✗ No se encontró el token de autenticación")
            return False

        except Exception as e:
            print(f"✗ Error de autenticación en FreshRSS: {e}")
            return False

    def list_categories(self):
        """Lista todas las categorías/tags disponibles"""
        if not self.auth_token:
            if not self.authenticate():
                return []

        url = f"{self.url}/api/greader.php/reader/api/0/tag/list"
        headers = {'Authorization': f'GoogleLogin auth={self.auth_token}'}
        params = {'output': 'json'}

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            categories = []
            for tag in data.get('tags', []):
                tag_id = tag.get('id', '')
                # Filtrar solo las categorías (labels)
                if '/label/' in tag_id:
                    category_name = tag_id.split('/label/')[-1]
                    categories.append({
                        'id': tag_id,
                        'name': category_name
                    })

            return categories
        except Exception as e:
            print(f"✗ Error al listar categorías: {e}")
            return []

    def list_feeds(self):
        """Lista todos los feeds/suscripciones"""
        if not self.auth_token:
            if not self.authenticate():
                return []

        url = f"{self.url}/api/greader.php/reader/api/0/subscription/list"
        headers = {'Authorization': f'GoogleLogin auth={self.auth_token}'}
        params = {'output': 'json'}

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            feeds = []
            for sub in data.get('subscriptions', []):
                feed_id = sub.get('id', '')
                feeds.append({
                    'id': feed_id,
                    'title': sub.get('title', ''),
                    'categories': sub.get('categories', [])
                })

            return feeds
        except Exception as e:
            print(f"✗ Error al listar feeds: {e}")
            return []

    def get_articles(self, stream_id=None, limit=10, unread_only=True):
        """
        Obtiene artículos de FreshRSS

        stream_id puede ser:
        - None o 'reading-list': todos los artículos
        - 'user/-/label/CATEGORIA': artículos de una categoría
        - 'feed/FEED_ID': artículos de un feed específico
        """
        if not self.auth_token:
            if not self.authenticate():
                return []

        # Construir URL del stream
        if stream_id:
            if stream_id == 'reading-list':
                stream_path = 'reading-list'
            elif stream_id.startswith('user/-/label/'):
                # Categoría específica
                stream_path = f"contents/{stream_id}"
            elif stream_id.startswith('feed/'):
                # Feed específico
                stream_path = f"contents/{stream_id}"
            else:
                stream_path = f"contents/{stream_id}"
        else:
            stream_path = 'reading-list'

        url = f"{self.url}/api/greader.php/reader/api/0/stream/{stream_path}"

        headers = {'Authorization': f'GoogleLogin auth={self.auth_token}'}
        params = {
            'n': limit,
            'output': 'json'
        }

        if unread_only:
            params['xt'] = 'user/-/state/com.google/read'

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()

            data = response.json()
            articles = data.get('items', [])
            return articles

        except Exception as e:
            print(f"✗ Error al obtener artículos: {e}")
            return []


class PodcastFeedGenerator:
    """Genera un feed RSS/Podcast simple"""

    def __init__(self, output_dir, base_url, title="Mis Artículos TTS", description="Artículos convertidos a audio", image_url=None, author=None):
        self.output_dir = output_dir
        self.base_url = base_url.rstrip('/')
        self.title = title
        self.description = description
        self.image_url = image_url
        self.author = author
        self.episodes = []

    def get_file_size(self, filepath):
        """Obtiene el tamaño del archivo en bytes"""
        try:
            return os.path.getsize(filepath)
        except:
            return 0

    def get_audio_duration(self, filepath):
        """Intenta obtener la duración del audio"""
        try:
            from mutagen.mp3 import MP3
            audio = MP3(filepath)
            return int(audio.info.length)
        except:
            # Estimación basada en tamaño (1 MB ≈ 60 segundos)
            size_mb = self.get_file_size(filepath) / (1024 * 1024)
            return int(size_mb * 60)

    def add_episode(self, title, filepath, description="", category=""):
        """Añade un episodio al feed"""
        if not os.path.exists(filepath):
            return

        filename = os.path.basename(filepath)
        url = f"{self.base_url}/{filename}"

        episode = {
            'title': title,
            'description': description or title,
            'url': url,
            'size': self.get_file_size(filepath),
            'duration': self.get_audio_duration(filepath),
            'pubDate': datetime.fromtimestamp(os.path.getmtime(filepath)),
            'category': category
        }

        self.episodes.append(episode)

    def generate_rss(self, output_file="podcast.xml"):
        """Genera el archivo RSS del podcast"""
        rss = Element('rss', {'version': '2.0', 'xmlns:itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'})
        channel = SubElement(rss, 'channel')

        SubElement(channel, 'title').text = self.title
        SubElement(channel, 'description').text = self.description
        SubElement(channel, 'link').text = self.base_url
        SubElement(channel, 'language').text = 'es'
        SubElement(channel, 'lastBuildDate').text = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')

        # Añadir autor si está disponible
        if self.author:
            SubElement(channel, 'itunes:author').text = self.author

        # Añadir imagen si está disponible
        if self.image_url:
            SubElement(channel, 'itunes:image', {'href': self.image_url})
            image_elem = SubElement(channel, 'image')
            SubElement(image_elem, 'url').text = self.image_url
            SubElement(image_elem, 'title').text = self.title
            SubElement(image_elem, 'link').text = self.base_url

        # Ordenar episodios por fecha (más reciente primero)
        sorted_episodes = sorted(self.episodes, key=lambda x: x['pubDate'], reverse=True)

        for episode in sorted_episodes:
            item = SubElement(channel, 'item')
            SubElement(item, 'title').text = episode['title']
            SubElement(item, 'description').text = episode['description']
            SubElement(item, 'pubDate').text = episode['pubDate'].strftime('%a, %d %b %Y %H:%M:%S +0000')
            SubElement(item, 'enclosure', {
                'url': episode['url'],
                'length': str(episode['size']),
                'type': 'audio/mpeg'
            })
            SubElement(item, 'guid').text = episode['url']
            if episode['category']:
                SubElement(item, 'category').text = episode['category']

        xml_str = minidom.parseString(tostring(rss, encoding='utf-8')).toprettyxml(indent="  ", encoding='utf-8')

        output_path = os.path.join(self.output_dir, output_file)
        with open(output_path, 'wb') as f:
            f.write(xml_str)

        print(f"\n✓ Feed RSS generado: {output_path}")
        print(f"✓ URL del feed: {self.base_url}/{output_file}")
        print(f"✓ Episodios: {len(self.episodes)}")

        return output_path


def print_available_voices():
    """Muestra las voces disponibles para edge-tts"""
    try:
        import edge_tts
        print("\n=== Voces disponibles para edge-tts ===")
        print("\nEspañol:")
        spanish_voices = [
            "es-ES-AlvaroNeural (Hombre, España)",
            "es-ES-ElviraNeural (Mujer, España)",
            "es-ES-AbrilNeural (Mujer, España)",
            "es-MX-DaliaNeural (Mujer, México)",
            "es-MX-JorgeNeural (Hombre, México)",
            "es-AR-ElenaNeural (Mujer, Argentina)",
            "es-AR-TomasNeural (Hombre, Argentina)",
        ]
        for voice in spanish_voices:
            print(f"  - {voice}")

        print("\nInglés:")
        english_voices = [
            "en-US-AriaNeural (Mujer, US)",
            "en-US-GuyNeural (Hombre, US)",
            "en-GB-SoniaNeural (Mujer, UK)",
            "en-GB-RyanNeural (Hombre, UK)",
        ]
        for voice in english_voices:
            print(f"  - {voice}")

        print("\nPara ver todas las voces disponibles, ejecuta:")
        print("  edge-tts --list-voices")

    except ImportError:
        print("edge-tts no está instalado. Instálalo con: pip install edge-tts")


def main():
    parser = argparse.ArgumentParser(
        description='Convierte artículos de Wallabag y FreshRSS a MP3 con TTS mejorado',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  # Usar edge-tts (mejor calidad)
  python3 articles_to_mp3.py --tts edge

  # Usar edge-tts con voz específica
  python3 articles_to_mp3.py --tts edge --voice es-ES-ElviraNeural

  # Traducir al español automáticamente
  python3 articles_to_mp3.py --language es

  # No omitir archivos existentes
  python3 articles_to_mp3.py --no-skip-existing

  # Ver voces disponibles
  python3 articles_to_mp3.py --list-voices

  # Listar categorías y feeds de FreshRSS
  python3 articles_to_mp3.py --freshrss-list
        """
    )

    parser.add_argument('--config', default='config.json',
                       help='Archivo de configuración JSON')
    parser.add_argument('--output', default='audio_articles',
                       help='Directorio de salida para los MP3')
    parser.add_argument('--limit', type=int, default=10,
                       help='Número máximo de artículos (si no se especifica en config)')
    parser.add_argument('--lang', default='es',
                       help='Idioma para gTTS (es, en, fr, etc.)')
    parser.add_argument('--source', choices=['wallabag', 'freshrss', 'both'],
                       default='both', help='Fuente de artículos')
    parser.add_argument('--tts', choices=['gtts', 'edge'],
                       default='gtts', help='Motor TTS a usar (gtts = estable, edge = mejor calidad)')
    parser.add_argument('--voice', default='es-ES-AlvaroNeural',
                       help='Voz para edge-tts (ej: es-ES-ElviraNeural)')
    parser.add_argument('--skip-existing', dest='skip_existing', action='store_true',
                       help='Omitir archivos que ya existen (por defecto)')
    parser.add_argument('--no-skip-existing', dest='skip_existing', action='store_false',
                       help='No omitir archivos existentes, crear versiones con timestamp')
    parser.add_argument('--language', choices=['es', 'en', 'fr', 'de', 'it', 'pt'],
                       help='Idioma destino para traducción automática (es, en, fr, de, it, pt). Si se especifica, se detectará el idioma del artículo y se traducirá si es necesario')
    parser.add_argument('--list-voices', action='store_true',
                       help='Muestra las voces disponibles para edge-tts')
    parser.add_argument('--freshrss-list', action='store_true',
                       help='Lista categorías y feeds de FreshRSS')
    parser.add_argument('--generate-feed', action='store_true',
                       help='Generar feed RSS/Podcast')
    parser.add_argument('--base-url', default='http://localhost:8005',
                       help='URL base para el feed RSS')
    parser.add_argument('--feed-title', default='Mis Artículos TTS',
                       help='Título del podcast')
    parser.add_argument('--feed-description', default='Artículos convertidos a audio',
                       help='Descripción del podcast')

    parser.set_defaults(skip_existing=True)

    args = parser.parse_args()

    # Mostrar voces disponibles
    if args.list_voices:
        print_available_voices()
        return

    # Cargar configuración
    if not os.path.exists(args.config):
        print(f"✗ No se encuentra el archivo de configuración: {args.config}")
        print("\nCrea un archivo config.json. Ver config.json.example para la estructura.")
        return

    with open(args.config, 'r') as f:
        config = json.load(f)

    # Listar categorías y feeds de FreshRSS
    if args.freshrss_list:
        if 'freshrss' not in config:
            print("✗ No hay configuración de FreshRSS en config.json")
            return

        fr_config = config['freshrss']
        freshrss = FreshRSSClient(
            fr_config['url'],
            fr_config['username'],
            fr_config['password']
        )

        print("\n=== CATEGORÍAS ===")
        categories = freshrss.list_categories()
        if categories:
            for cat in categories:
                print(f"  - {cat['name']}")
        else:
            print("  No se encontraron categorías")

        print("\n=== FEEDS ===")
        feeds = freshrss.list_feeds()
        if feeds:
            for feed in feeds:
                categories_str = ", ".join([c.get('label', '') for c in feed.get('categories', [])])
                print(f"  - {feed['title']}")
                print(f"    ID: {feed['id']}")
                if categories_str:
                    print(f"    Categorías: {categories_str}")
        else:
            print("  No se encontraron feeds")

        print("\nPara usar categorías/feeds específicos, edita tu config.json")
        return

    # Verificar dependencias para traducción
    if args.language:
        try:
            import langdetect
            from deep_translator import GoogleTranslator
            print(f"\n✓ Traducción automática habilitada (idioma destino: {args.language})")
        except ImportError as e:
            print(f"✗ Error: Falta instalar dependencias para traducción")
            print("  Instala con: pip install langdetect deep-translator --break-system-packages")
            return

    # Verificar que edge-tts esté instalado si se solicita
    if args.tts == 'edge':
        try:
            import edge_tts
        except ImportError:
            print("✗ edge-tts no está instalado. Instálalo con:")
            print("  pip install edge-tts --break-system-packages")
            print("\nUsando gTTS como alternativa...")
            args.tts = 'gtts'

    # Inicializar convertidor
    converter = ArticleToMP3Converter(
        output_dir=args.output,
        tts_engine=args.tts,
        voice=args.voice,
        skip_existing=args.skip_existing,
        target_language=args.language
    )

    # Inicializar generador de feed si se solicita
    feed_generator = None
    if args.generate_feed:
        feed_generator = PodcastFeedGenerator(
            output_dir=args.output,
            base_url=args.base_url,
            title=args.feed_title,
            description=args.feed_description
        )

    articles_processed = 0

    # Procesar Wallabag
    if args.source in ['wallabag', 'both'] and 'wallabag' in config:
        print("\n=== WALLABAG ===")
        wb_config = config['wallabag']
        wallabag = WallabagClient(
            wb_config['url'],
            wb_config['client_id'],
            wb_config['client_secret'],
            wb_config['username'],
            wb_config['password']
        )

        limit = wb_config.get('limit', args.limit)
        articles = wallabag.get_articles(archive=0, limit=limit)

        # Obtener idioma original de config si existe
        original_language = wb_config.get('original-language')

        for article in articles:
            title = article.get('title', 'Sin título')
            content = article.get('content', '')

            if content:
                text = converter.clean_text(content)
                if text:
                    filepath = converter.process_and_convert(
                        text,
                        title,
                        original_language=original_language,
                        lang=args.lang
                    )
                    if filepath:
                        articles_processed += 1
                        if feed_generator:
                            feed_generator.add_episode(
                                title=title,
                                filepath=filepath,
                                description=f"De Wallabag",
                                category="Wallabag"
                            )

    # Procesar FreshRSS
    if args.source in ['freshrss', 'both'] and 'freshrss' in config:
        print("\n=== FRESHRSS ===")
        fr_config = config['freshrss']
        freshrss = FreshRSSClient(
            fr_config['url'],
            fr_config['username'],
            fr_config['password']
        )

        # Obtener configuración de categorías y feeds
        categories = fr_config.get('categories', [])
        feeds = fr_config.get('feeds', [])
        default_limit = fr_config.get('limit', args.limit)
        default_original_language = fr_config.get('original-language')

        # Si no hay categorías ni feeds específicos, obtener de reading-list
        if not categories and not feeds:
            print("Obteniendo artículos de reading-list (todos)...")
            articles = freshrss.get_articles(
                stream_id='reading-list',
                limit=default_limit,
                unread_only=fr_config.get('unread_only', True)
            )

            for article in articles:
                title = article.get('title', 'Sin título')
                content = ''
                if 'summary' in article and 'content' in article['summary']:
                    content = article['summary']['content']
                elif 'content' in article and 'content' in article['content']:
                    content = article['content']['content']

                if content:
                    text = converter.clean_text(content)
                    if text:
                        filepath = converter.process_and_convert(
                            text,
                            title,
                            original_language=default_original_language,
                            lang=args.lang
                        )
                        if filepath:
                            articles_processed += 1
                            if feed_generator:
                                feed_generator.add_episode(
                                    title=title,
                                    filepath=filepath,
                                    description=title,
                                    category="General"
                                )

        # Procesar categorías específicas
        for category in categories:
            cat_name = category.get('name')
            cat_limit = category.get('limit', default_limit)
            cat_voice = category.get('voice', args.voice)
            cat_original_language = category.get('original-language', default_original_language)

            print(f"\nObteniendo artículos de categoría: {cat_name} (límite: {cat_limit})...")
            stream_id = f"user/-/label/{cat_name}"
            articles = freshrss.get_articles(
                stream_id=stream_id,
                limit=cat_limit,
                unread_only=fr_config.get('unread_only', True)
            )

            print(f"✓ {len(articles)} artículos de '{cat_name}'")

            # Actualizar voz si es específica de la categoría
            if cat_voice != converter.voice:
                converter.voice = cat_voice

            for article in articles:
                title = article.get('title', 'Sin título')
                content = ''
                if 'summary' in article and 'content' in article['summary']:
                    content = article['summary']['content']
                elif 'content' in article and 'content' in article['content']:
                    content = article['content']['content']

                if content:
                    text = converter.clean_text(content)
                    if text:
                        filepath = converter.process_and_convert(
                            text,
                            f"[{cat_name}] {title}",
                            original_language=cat_original_language,
                            lang=args.lang
                        )
                        if filepath:
                            articles_processed += 1
                            if feed_generator:
                                feed_generator.add_episode(
                                    title=f"[{cat_name}] {title}",
                                    filepath=filepath,
                                    description=title,
                                    category=cat_name
                                )

        # Procesar feeds específicos
        for feed in feeds:
            feed_id = feed.get('id')
            feed_limit = feed.get('limit', default_limit)
            feed_name = feed.get('name', feed_id)
            feed_voice = feed.get('voice', args.voice)
            feed_original_language = feed.get('original-language', default_original_language)

            print(f"\nObteniendo artículos de feed: {feed_name} (límite: {feed_limit})...")
            articles = freshrss.get_articles(
                stream_id=feed_id,
                limit=feed_limit,
                unread_only=fr_config.get('unread_only', True)
            )

            print(f"✓ {len(articles)} artículos de '{feed_name}'")

            # Actualizar voz si es específica del feed
            if feed_voice != converter.voice:
                converter.voice = feed_voice

            for article in articles:
                title = article.get('title', 'Sin título')
                content = ''
                if 'summary' in article and 'content' in article['summary']:
                    content = article['summary']['content']
                elif 'content' in article and 'content' in article['content']:
                    content = article['content']['content']

                if content:
                    text = converter.clean_text(content)
                    if text:
                        filepath = converter.process_and_convert(
                            text,
                            f"[{feed_name}] {title}",
                            original_language=feed_original_language,
                            lang=args.lang
                        )
                        if filepath:
                            articles_processed += 1
                            if feed_generator:
                                feed_generator.add_episode(
                                    title=f"[{feed_name}] {title}",
                                    filepath=filepath,
                                    description=title,
                                    category=feed_name
                                )

    print(f"\n✓ Proceso completado. {articles_processed} artículos convertidos a MP3")
    print(f"✓ Motor TTS usado: {args.tts}")
    if args.tts == 'edge':
        print(f"✓ Voz usada: {args.voice}")
    if args.language:
        print(f"✓ Traducción automática: activada (destino: {args.language})")
    print(f"✓ Omitir existentes: {'Sí' if args.skip_existing else 'No'}")
    print(f"✓ Archivos guardados en: {args.output}")

    # Generar feed RSS si se solicitó
    if args.generate_feed and feed_generator and feed_generator.episodes:
        feed_generator.generate_rss()


if __name__ == "__main__":
    main()
