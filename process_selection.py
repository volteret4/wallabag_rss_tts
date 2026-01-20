#!/usr/bin/env python3
"""
Script para procesar artículos seleccionados desde la interfaz web
Lee selection.json y convierte los artículos seleccionados a MP3
"""

import os
import json
import argparse
import sys
import asyncio

# Importar las clases del script principal
# Asumiendo que articles_to_mp3.py está en el mismo directorio
try:
    from articles_to_mp3 import (
        ArticleToMP3Converter,
        WallabagClient,
        FreshRSSClient,
        PodcastFeedGenerator
    )
except ImportError:
    print("✗ Error: No se puede importar articles_to_mp3.py")
    print("  Asegúrate de que articles_to_mp3.py esté en el mismo directorio")
    sys.exit(1)


def load_config(config_file='config.json'):
    """Carga la configuración desde config.json"""
    if not os.path.exists(config_file):
        print(f"✗ No se encuentra {config_file}")
        print("  Se necesita config.json con las credenciales de Wallabag/FreshRSS")
        return None

    with open(config_file, 'r') as f:
        return json.load(f)


def load_selection(selection_file):
    """Carga los artículos seleccionados"""
    if not os.path.exists(selection_file):
        print(f"✗ No se encuentra {selection_file}")
        return None

    with open(selection_file, 'r') as f:
        return json.load(f)


def process_wallabag_articles(selection, config, converter, feed_generator=None):
    """Procesa artículos de Wallabag"""
    wallabag_articles = selection.get('wallabag', [])

    if not wallabag_articles:
        return 0

    if 'wallabag' not in config:
        print("⚠ No hay configuración de Wallabag en config.json")
        return 0

    print(f"\n=== WALLABAG: {len(wallabag_articles)} artículos ===")

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
        title = article_info.get('title', 'Sin título')

        print(f"\nProcesando {idx}/{len(wallabag_articles)}: {title}")

        # Obtener el artículo completo de Wallabag
        try:
            article = wallabag.get_article(article_id)

            if not article:
                print(f"  ✗ No se pudo obtener el artículo {article_id}")
                continue

            content = article.get('content', '')

            if not content:
                print(f"  ✗ Artículo sin contenido")
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
                    print(f"  ✓ Convertido: {os.path.basename(filepath)}")

                    if feed_generator:
                        feed_generator.add_episode(
                            title=title,
                            filepath=filepath,
                            description=f"De Wallabag",
                            category="Wallabag"
                        )

        except Exception as e:
            print(f"  ✗ Error procesando artículo {article_id}: {e}")

    return processed


def process_freshrss_articles(selection, config, converter, feed_generator=None):
    """Procesa artículos de FreshRSS"""
    freshrss_selection = selection.get('freshrss', {}).get('categories', {})

    if not freshrss_selection:
        return 0

    if 'freshrss' not in config:
        print("⚠ No hay configuración de FreshRSS en config.json")
        return 0

    # Contar total de artículos
    total_articles = sum(
        len(feed_articles)
        for category in freshrss_selection.values()
        for feed_articles in category.values()
    )

    print(f"\n=== FRESHRSS: {total_articles} artículos ===")

    fr_config = config['freshrss']
    freshrss = FreshRSSClient(
        fr_config['url'],
        fr_config['username'],
        fr_config['password']
    )

    processed = 0
    article_count = 0

    # Procesar por categoría y feed
    for category_name, feeds in freshrss_selection.items():
        print(f"\n📁 Categoría: {category_name}")

        for feed_id, articles in feeds.items():
            print(f"\n  📰 Feed: {feed_id} ({len(articles)} artículos)")

            for article_info in articles:
                article_count += 1
                article_id = article_info.get('id')
                title = article_info.get('title', 'Sin título')

                print(f"\n  Procesando {article_count}/{total_articles}: {title}")

                try:
                    # Obtener el artículo completo de FreshRSS
                    # Usando el ID del artículo directamente
                    articles_full = freshrss.get_articles(
                        stream_id=feed_id,
                        limit=100
                    )

                    # Buscar el artículo específico
                    article = None
                    for art in articles_full:
                        if art.get('id') == article_id:
                            article = art
                            break

                    if not article:
                        print(f"    ✗ No se pudo obtener el artículo")
                        continue

                    # Extraer contenido
                    content = ''
                    if 'summary' in article and 'content' in article['summary']:
                        content = article['summary']['content']
                    elif 'content' in article and 'content' in article['content']:
                        content = article['content']['content']

                    if not content:
                        print(f"    ✗ Artículo sin contenido")
                        continue

                    # Limpiar y convertir
                    text = converter.clean_text(content)

                    if text:
                        original_language = fr_config.get('original-language')
                        filepath = converter.process_and_convert(
                            text,
                            f"[{category_name}] {title}",
                            original_language=original_language
                        )

                        if filepath:
                            processed += 1
                            print(f"    ✓ Convertido: {os.path.basename(filepath)}")

                            if feed_generator:
                                feed_generator.add_episode(
                                    title=f"[{category_name}] {title}",
                                    filepath=filepath,
                                    description=title,
                                    category=category_name
                                )

                except Exception as e:
                    print(f"    ✗ Error procesando artículo: {e}")

    return processed


def main():
    parser = argparse.ArgumentParser(
        description='Procesa artículos seleccionados y los convierte a MP3'
    )
    parser.add_argument('--selection', default='selection.json',
                       help='Archivo de selección JSON')
    parser.add_argument('--config', default='config.json',
                       help='Archivo de configuración JSON')
    parser.add_argument('--output', default='audio_articles',
                       help='Directorio de salida para los MP3')
    parser.add_argument('--tts', choices=['gtts', 'edge'],
                       default='edge', help='Motor TTS a usar')
    parser.add_argument('--voice', default='es-ES-AlvaroNeural',
                       help='Voz para edge-tts')
    parser.add_argument('--skip-existing', action='store_true', default=True,
                       help='Omitir archivos que ya existen')
    parser.add_argument('--language', choices=['es', 'en', 'fr', 'de', 'it', 'pt'],
                       help='Idioma destino para traducción automática')
    parser.add_argument('--generate-feed', action='store_true',
                       help='Generar feed RSS/Podcast')
    parser.add_argument('--base-url', default='https://podcast.pollete.duckdns.org',
                       help='URL base para el feed RSS')
    parser.add_argument('--feed-title', default='Mis Artículos TTS',
                       help='Título del podcast')
    parser.add_argument('--feed-description', default='Artículos convertidos a audio',
                       help='Descripción del podcast')

    args = parser.parse_args()

    # Cargar configuración
    config = load_config(args.config)
    if not config:
        return 1

    # Cargar selección
    selection = load_selection(args.selection)
    if not selection:
        return 1

    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   🎙️  Conversión de Artículos Seleccionados a MP3            ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝

⚙️  Motor TTS: {args.tts}
🔊 Voz: {args.voice}
📁 Salida: {args.output}
🔄 Omitir existentes: {args.skip_existing}
    """)

    if args.language:
        print(f"🌍 Traducción automática: {args.language}")

    # Verificar edge-tts si es necesario
    if args.tts == 'edge':
        try:
            import edge_tts
        except ImportError:
            print("✗ edge-tts no está instalado. Cambiando a gTTS...")
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

    # Procesar artículos
    total_processed = 0

    # Wallabag
    wb_processed = process_wallabag_articles(selection, config, converter, feed_generator)
    total_processed += wb_processed

    # FreshRSS
    fr_processed = process_freshrss_articles(selection, config, converter, feed_generator)
    total_processed += fr_processed

    # Resumen
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   ✓ Proceso Completado                                       ║
║                                                               ║
║   📊 {total_processed} artículos convertidos exitosamente                  ║
║   📁 Archivos guardados en: {args.output:<30} ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """)

    # Generar feed RSS si se solicitó
    if args.generate_feed and feed_generator and feed_generator.episodes:
        print("\n🎙️  Generando feed RSS para podcast...")
        feed_generator.generate_rss()
        print(f"✓ Feed RSS generado: {os.path.join(args.output, 'podcast.xml')}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
