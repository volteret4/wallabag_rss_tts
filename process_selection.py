#!/usr/bin/env python3
"""
Script para procesar artÃƒÂ­culos seleccionados desde la interfaz web
Lee selection.json y convierte los artÃƒÂ­culos seleccionados a MP3
"""

import os
import json
import argparse
import sys
import asyncio
import glob
import shutil
import tempfile
import subprocess

# Importar las clases del script principal
# Asumiendo que articles_to_mp3.py estÃƒÂ¡ en el mismo directorio
try:
    from articles_to_mp3 import (
        ArticleToMP3Converter,
        WallabagClient,
        FreshRSSClient,
        PodcastFeedGenerator,
        generate_feed_from_existing_files
    )
except ImportError:
    print("Ã¢Å“â€” Error: No se puede importar articles_to_mp3.py")
    print("  AsegÃƒÂºrate de que articles_to_mp3.py estÃƒÂ© en el mismo directorio")
    sys.exit(1)



# ============================================================================
# Funciones para procesamiento de audio de YouTube
# ============================================================================

def extract_youtube_urls(html_content):
    """
    Extrae URLs de YouTube del contenido HTML
    Soporta varios formatos:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    - iframes de YouTube
    """
    youtube_urls = []

    # PatrÃ³n para URLs directas
    patterns = [
        r'https?://(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]+)',
        r'https?://youtu\.be/([a-zA-Z0-9_-]+)',
        r'https?://(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]+)',
    ]

    for pattern in patterns:
        matches = re.finditer(pattern, html_content)
        for match in matches:
            video_id = match.group(1)
            url = f"https://www.youtube.com/watch?v={video_id}"
            if url not in youtube_urls:
                youtube_urls.append(url)

    return youtube_urls


def download_youtube_audio(url, output_dir, title_prefix="yt_audio"):
    """
    Descarga el audio de un video de YouTube usando yt-dlp

    Returns:
        str: Ruta al archivo de audio descargado, o None si falla
    """
    try:
        # Crear nombre de archivo temporal
        temp_filename = os.path.join(output_dir, f"{title_prefix}_%(id)s.%(ext)s")

        # Comando yt-dlp para descargar solo audio en formato MP3
        cmd = [
            'yt-dlp',
            '--extract-audio',
            '--audio-format', 'mp3',
            '--audio-quality', '0',  # Mejor calidad
            '-o', temp_filename,
            '--no-playlist',
            '--quiet',
            '--no-warnings',
            url
        ]

        # Ejecutar yt-dlp
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            # Buscar el archivo descargado
            # yt-dlp cambia el nombre del archivo, asÃ­ que buscamos archivos .mp3 recientes
            import glob
            pattern = os.path.join(output_dir, f"{title_prefix}_*.mp3")
            files = glob.glob(pattern)

            if files:
                # Ordenar por tiempo de modificaciÃ³n y tomar el mÃ¡s reciente
                latest_file = max(files, key=os.path.getmtime)
                print(f"  âœ“ Audio de YouTube descargado: {os.path.basename(latest_file)}")
                return latest_file
            else:
                print(f"  âœ— No se encontrÃ³ el archivo descargado")
                return None
        else:
            print(f"  âœ— Error descargando audio de YouTube: {result.stderr}")
            return None

    except Exception as e:
        print(f"  âœ— Error al descargar audio de YouTube: {e}")
        return None


def combine_audio_files(audio_files, output_file):
    """
    Combina mÃºltiples archivos de audio en uno solo usando ffmpeg

    Args:
        audio_files: Lista de rutas a archivos de audio (en orden)
        output_file: Ruta al archivo de salida

    Returns:
        bool: True si tuvo Ã©xito, False si fallÃ³
    """
    if not audio_files:
        return False

    if len(audio_files) == 1:
        # Si solo hay un archivo, simplemente copiarlo
        import shutil
        shutil.copy(audio_files[0], output_file)
        return True

    try:
        # Crear un archivo de lista temporal para ffmpeg
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            list_file = f.name
            for audio_file in audio_files:
                # Escapar comillas simples en el nombre del archivo
                safe_path = audio_file.replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")

        # Comando ffmpeg para concatenar
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', list_file,
            '-c', 'copy',
            '-y',  # Sobrescribir si existe
            output_file
        ]

        # Ejecutar ffmpeg
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            stderr=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL
        )

        # Limpiar archivo temporal
        os.unlink(list_file)

        if result.returncode == 0:
            print(f"  âœ“ Audios combinados exitosamente")
            return True
        else:
            print(f"  âœ— Error combinando audios con ffmpeg")
            return False

    except Exception as e:
        print(f"  âœ— Error al combinar audios: {e}")
        return False


def check_dependencies():
    """
    Verifica que yt-dlp y ffmpeg estÃ©n instalados

    Returns:
        tuple: (yt-dlp_available, ffmpeg_available)
    """
    yt_dlp_available = False
    ffmpeg_available = False

    try:
        result = subprocess.run(
            ['yt-dlp', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        yt_dlp_available = result.returncode == 0
    except:
        pass

    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        ffmpeg_available = result.returncode == 0
    except:
        pass

    return yt_dlp_available, ffmpeg_available


def load_config(config_file='config.json'):
    """Carga la configuraciÃƒÂ³n desde config.json"""
    if not os.path.exists(config_file):
        print(f"Ã¢Å“â€” No se encuentra {config_file}")
        print("  Se necesita config.json con las credenciales de Wallabag/FreshRSS")
        return None

    with open(config_file, 'r') as f:
        return json.load(f)


def load_selection(selection_file):
    """Carga los artÃƒÂ­culos seleccionados"""
    if not os.path.exists(selection_file):
        print(f"Ã¢Å“â€” No se encuentra {selection_file}")
        return None

    with open(selection_file, 'r') as f:
        return json.load(f)


def process_wallabag_articles(selection, config, converter, feed_generator=None, mark_as_read=False):
    """Procesa artÃƒÂ­culos de Wallabag"""
    wallabag_articles = selection.get('wallabag', [])

    if not wallabag_articles:
        return 0

    if 'wallabag' not in config:
        print("Ã¢Å¡Â  No hay configuraciÃƒÂ³n de Wallabag en config.json")
        return 0

    print(f"\n=== WALLABAG: {len(wallabag_articles)} artÃƒÂ­culos ===")

    wb_config = config['wallabag']
    wallabag = WallabagClient(
        wb_config['url'],
        wb_config['client_id'],
        wb_config['client_secret'],
        wb_config['username'],
        wb_config['password']
    )

    processed = 0

    for idx, article_info in enumerate(wallabag_articles, 1):
        article_id = article_info.get('id')
        title = article_info.get('title', 'Sin tÃƒÂ­tulo')

        print(f"\nProcesando {idx}/{len(wallabag_articles)}: {title}")

        # Obtener el artÃƒÂ­culo completo de Wallabag
        try:
            article = wallabag.get_article(article_id)

            if not article:
                print(f"  Ã¢Å“â€” No se pudo obtener el artÃƒÂ­culo {article_id}")
                continue

            content = article.get('content', '')

            if not content:
                print(f"  Ã¢Å“â€” ArtÃƒÂ­culo sin contenido")
                continue

            # Limpiar y convertir
            text = converter.clean_text(content)

            if text:
                original_language = wb_config.get('original-language')
                filepath = converter.process_and_convert(
                    text,
                    title,
                    original_language=original_language
                )

                if filepath:
                    processed += 1
                    print(f"  Ã¢Å“â€œ Convertido: {os.path.basename(filepath)}")

                    if feed_generator:
                        feed_generator.add_episode(
                            title=title,
                            filepath=filepath,
                            description=f"De Wallabag",
                            category="Wallabag"
                        )

        except Exception as e:
            print(f"  Ã¢Å“â€” Error procesando artÃƒÂ­culo {article_id}: {e}")

    return processed


def process_freshrss_articles(selection, config, converter, feed_generator=None, mark_as_read=False):
    """Procesa artÃƒÂ­culos de FreshRSS"""
    freshrss_selection = selection.get('freshrss', {}).get('categories', {})

    if not freshrss_selection:
        return 0

    if 'freshrss' not in config:
        print("Ã¢Å¡Â  No hay configuraciÃƒÂ³n de FreshRSS en config.json")
        return 0

    # Contar total de artÃƒÂ­culos
    total_articles = sum(
        len(feed_articles)
        for category in freshrss_selection.values()
        for feed_articles in category.values()
    )

    print(f"\n=== FRESHRSS: {total_articles} artÃƒÂ­culos ===")

    fr_config = config['freshrss']
    freshrss = FreshRSSClient(
        fr_config['url'],
        fr_config['username'],
        fr_config['password']
    )

    # Cargar articles_data.json para obtener nombres de feeds
    feed_names = {}
    try:
        articles_data_file = 'articles_data.json'
        if os.path.exists(articles_data_file):
            with open(articles_data_file, 'r') as f:
                articles_data = json.load(f)

            # Construir un mapa de feed_id -> feed_title
            for category in articles_data.get('freshrss', {}).get('categories', []):
                for feed in category.get('feeds', []):
                    feed_names[feed['id']] = feed['title']

            print(f"Ã°Å¸â€œÅ¡ Cargados nombres de {len(feed_names)} feeds")
        else:
            print("Ã¢Å¡Â Ã¯Â¸Â  No se encuentra articles_data.json, los tÃƒÂ­tulos no incluirÃƒÂ¡n el nombre del feed")
    except Exception as e:
        print(f"Ã¢Å¡Â Ã¯Â¸Â  Error cargando nombres de feeds: {e}")

    processed = 0
    article_count = 0

    # Procesar por categorÃƒÂ­a y feed
    for category_name, feeds in freshrss_selection.items():
        print(f"\nÃ°Å¸â€œÂ CategorÃƒÂ­a: {category_name}")

        for feed_id, articles in feeds.items():
            # Obtener nombre del feed
            feed_name = feed_names.get(feed_id, feed_id.split('/')[-1])  # Fallback al ID

            print(f"\n  Ã°Å¸â€œÂ° Feed: {feed_name} ({len(articles)} artÃƒÂ­culos)")

            for article_info in articles:
                article_count += 1
                article_id = article_info.get('id')
                title = article_info.get('title', 'Sin tÃƒÂ­tulo')

                print(f"\n  Procesando {article_count}/{total_articles}: {title}")

                try:
                    # Obtener el artÃƒÂ­culo completo de FreshRSS
                    # Usando el ID del artÃƒÂ­culo directamente
                    articles_full = freshrss.get_articles(
                        stream_id=feed_id,
                        limit=100
                    )

                    # Buscar el artÃƒÂ­culo especÃƒÂ­fico
                    article = None
                    for art in articles_full:
                        if art.get('id') == article_id:
                            article = art
                            break

                    if not article:
                        print(f"    Ã¢Å“â€” No se pudo obtener el artÃƒÂ­culo")
                        continue

                    # Extraer contenido
                    content = ''
                    if 'summary' in article and 'content' in article['summary']:
                        content = article['summary']['content']
                    elif 'content' in article and 'content' in article['content']:
                        content = article['content']['content']

                    if not content:
                        print(f"    Ã¢Å“â€” ArtÃƒÂ­culo sin contenido")
                        continue

                    # Limpiar y convertir
                    text = converter.clean_text(content)

                    if text:
                        original_language = fr_config.get('original-language')

                        # Formato: [CategorÃƒÂ­a] Nombre del Feed - TÃƒÂ­tulo del artÃƒÂ­culo
                        episode_title = f"[{category_name}] {feed_name} - {title}"

                        filepath = converter.process_and_convert(
                            text,
                            episode_title,
                            original_language=original_language
                        )

                        if filepath:
                            processed += 1
                            print(f"    Ã¢Å“â€œ Convertido: {os.path.basename(filepath)}")

                            if feed_generator:
                                feed_generator.add_episode(
                                    title=episode_title,
                                    filepath=filepath,
                                    description=f"{feed_name}: {title}",
                                    category=category_name
                                )

                except Exception as e:
                    print(f"    Ã¢Å“â€” Error procesando artÃƒÂ­culo: {e}")

    return processed


def main():
    parser = argparse.ArgumentParser(
        description='Procesa artÃƒÂ­culos seleccionados y los convierte a MP3'
    )
    parser.add_argument('--selection', default='selection.json',
                       help='Archivo de selecciÃƒÂ³n JSON')
    parser.add_argument('--config', default='config.json',
                       help='Archivo de configuraciÃƒÂ³n JSON')
    parser.add_argument('--output', default='audio_articles',
                       help='Directorio de salida para los MP3')
    parser.add_argument('--tts', choices=['gtts', 'edge'],
                       default='edge', help='Motor TTS a usar')
    parser.add_argument('--voice', default='es-ES-AlvaroNeural',
                       help='Voz para edge-tts')
    parser.add_argument('--skip-existing', action='store_true', default=True,
                       help='Omitir archivos que ya existen')
    parser.add_argument('--language', choices=['es', 'en', 'fr', 'de', 'it', 'pt'],
                       help='Idioma destino para traducciÃƒÂ³n automÃƒÂ¡tica')
    parser.add_argument('--generate-feed', action='store_true',
                       help='Generar feed RSS/Podcast')
    parser.add_argument('--base-url', default='https://podcast.pollete.duckdns.org',
                       help='URL base para el feed RSS')
    parser.add_argument('--feed-title', default='Mis ArtÃƒÂ­culos TTS',
                       help='TÃƒÂ­tulo del podcast')
    parser.add_argument('--feed-description', default='ArtÃƒÂ­culos convertidos a audio',
                       help='DescripciÃƒÂ³n del podcast')
    parser.add_argument('--only-xml', action='store_true',
                       help='Solo generar podcast.xml desde archivos MP3 existentes')

    args = parser.parse_args()

    # Si solo se quiere generar el XML
    if args.only_xml:
        feed_dir = os.path.dirname(args.output) if args.output not in ['.', ''] else '.'
        success = generate_feed_from_existing_files(
            output_dir=args.output,
            base_url=args.base_url,
            feed_title=args.feed_title,
            feed_description=args.feed_description,
            feed_dir=feed_dir
        )
        return 0 if success else 1

    # Cargar configuraciÃƒÂ³n
    config = load_config(args.config)
    if not config:
        return 1

    # Cargar selecciÃƒÂ³n
    selection = load_selection(args.selection)
    if not selection:
        return 1

    print(f"""
Ã¢â€¢â€Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢â€”
Ã¢â€¢â€˜                                                               Ã¢â€¢â€˜
Ã¢â€¢â€˜   Ã°Å¸Å½â„¢Ã¯Â¸Â  ConversiÃƒÂ³n de ArtÃƒÂ­culos Seleccionados a MP3            Ã¢â€¢â€˜
Ã¢â€¢â€˜                                                               Ã¢â€¢â€˜
Ã¢â€¢Å¡Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â

Ã¢Å¡â„¢Ã¯Â¸Â  Motor TTS: {args.tts}
Ã°Å¸â€Å  Voz: {args.voice}
Ã°Å¸â€œÂ Salida: {args.output}
Ã°Å¸â€â€ž Omitir existentes: {args.skip_existing}
    """)

    if args.language:
        print(f"Ã°Å¸Å’Â TraducciÃƒÂ³n automÃƒÂ¡tica: {args.language}")

    # Verificar edge-tts si es necesario
    if args.tts == 'edge':
        try:
            import edge_tts
        except ImportError:
            print("Ã¢Å“â€” edge-tts no estÃƒÂ¡ instalado. Cambiando a gTTS...")
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

    # Procesar artÃƒÂ­culos
    total_processed = 0

    # Wallabag
    wb_processed = process_wallabag_articles(selection, config, converter, feed_generator, args.mark_as_read)
    total_processed += wb_processed

    # FreshRSS
    fr_processed = process_freshrss_articles(selection, config, converter, feed_generator, args.mark_as_read)
    total_processed += fr_processed

    # Resumen
    print(f"""
Ã¢â€¢â€Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢â€”
Ã¢â€¢â€˜                                                               Ã¢â€¢â€˜
Ã¢â€¢â€˜   Ã¢Å“â€œ Proceso Completado                                       Ã¢â€¢â€˜
Ã¢â€¢â€˜                                                               Ã¢â€¢â€˜
Ã¢â€¢â€˜   Ã°Å¸â€œÅ  {total_processed} artÃƒÂ­culos convertidos exitosamente                  Ã¢â€¢â€˜
Ã¢â€¢â€˜   Ã°Å¸â€œÂ Archivos guardados en: {args.output:<30} Ã¢â€¢â€˜
Ã¢â€¢â€˜                                                               Ã¢â€¢â€˜
Ã¢â€¢Å¡Ã¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢ÂÃ¢â€¢Â
    """)

    # Generar feed RSS si se solicitÃƒÂ³
    if args.generate_feed and feed_generator and feed_generator.episodes:
        print("\nÃ°Å¸Å½â„¢Ã¯Â¸Â  Generando feed RSS para podcast...")
        feed_generator.generate_rss()
        print(f"Ã¢Å“â€œ Feed RSS generado: {os.path.join(args.output, 'podcast.xml')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
