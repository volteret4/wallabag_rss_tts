#!/usr/bin/env python3
"""
Script mejorado para procesar artículos seleccionados desde la interfaz web
Lee selection.json con opciones personalizadas por artículo y convierte a MP3
Versión 2.0: Soporte para opciones individuales por artículo
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
import re

# Importar las clases del script principal
try:
    from articles_to_mp3 import (
        ArticleToMP3Converter,
        WallabagClient,
        FreshRSSClient,
        PodcastFeedGenerator,
        generate_feed_from_existing_files,
        extract_youtube_urls,
        download_youtube_audio,
        combine_audio_files,
        get_audio_duration_ms,
        add_chapters_to_mp3
    )
except ImportError:
    print("✗ Error: No se puede importar articles_to_mp3.py")
    print("  Asegúrate de que articles_to_mp3.py esté en el mismo directorio")
    sys.exit(1)


def load_config(config_file='config.json'):
    """Carga el archivo de configuración"""
    if not os.path.exists(config_file):
        print(f"✗ No se encuentra el archivo de configuración: {config_file}")
        return None

    with open(config_file, 'r') as f:
        return json.load(f)


def load_selection(selection_file='selection.json'):
    """Carga el archivo de selección"""
    if not os.path.exists(selection_file):
        print(f"✗ No se encuentra el archivo de selección: {selection_file}")
        return None

    with open(selection_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def process_wallabag_articles(selection, config, default_options, feed_generator=None):
    """Procesa artículos de Wallabag con opciones personalizadas"""

    if 'wallabag' not in config:
        print("ℹ️  Wallabag no configurado, saltando...")
        return 0

    wallabag_selection = selection.get('wallabag', [])
    if not wallabag_selection:
        print("ℹ️  No hay artículos de Wallabag seleccionados")
        return 0

    print("\n=== WALLABAG ===")
    print(f"📋 {len(wallabag_selection)} artículos seleccionados")

    wb_config = config['wallabag']
    wallabag = WallabagClient(
        wb_config['url'],
        wb_config['client_id'],
        wb_config['client_secret'],
        wb_config['username'],
        wb_config['password']
    )

    processed = 0
    total_articles = len(wallabag_selection)

    for idx, article_info in enumerate(wallabag_selection, 1):
        article_id = article_info.get('id')
        title = article_info.get('title', 'Sin título')

        # Opciones específicas del artículo (con fallback a opciones por defecto)
        article_options = {
            'voice': article_info.get('voice', default_options['default_voice']),
            'language': article_info.get('language', default_options['default_language']),
            'include_youtube': article_info.get('include_youtube', default_options.get('include_youtube', False)),
            'tts_engine': article_info.get('tts_engine', default_options.get('tts_engine', 'edge'))
        }

        print(f"\nProcesando {idx}/{total_articles}: {title}")
        print(f"  🎤 Voz: {article_options['voice']}")
        print(f"  🌍 Idioma: {article_options['language']}")
        if article_options['include_youtube']:
            print(f"  📺 YouTube: Habilitado")

        try:
            # Obtener artículo completo
            article = wallabag.get_article(article_id)
            if not article:
                print(f"  ✗ No se pudo obtener el artículo")
                continue

            content = article.get('content', '')
            if not content:
                print(f"  ✗ Artículo sin contenido")
                continue

            # Crear convertidor con opciones del artículo
            converter = ArticleToMP3Converter(
                output_dir=default_options['output_dir'],
                tts_engine=article_options['tts_engine'],
                voice=article_options['voice'],
                skip_existing=default_options.get('skip_existing', True),
                target_language=article_options['language']
            )

            # Limpiar texto
            text = converter.clean_text(content)

            if text:
                # Determinar si procesar con YouTube
                if article_options['include_youtube']:
                    filepath = converter.process_and_convert_with_youtube(
                        text,
                        content,  # HTML original
                        title,
                        original_language=wb_config.get('original-language'),
                        lang=article_options['language']
                    )
                else:
                    filepath = converter.process_and_convert(
                        text,
                        title,
                        original_language=wb_config.get('original-language'),
                        lang=article_options['language']
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
            print(f"  ✗ Error procesando artículo: {e}")

    print(f"\n✓ Wallabag: {processed}/{total_articles} artículos procesados")
    return processed


def process_freshrss_articles(selection, config, default_options, feed_generator=None):
    """Procesa artículos de FreshRSS con opciones personalizadas"""

    if 'freshrss' not in config:
        print("ℹ️  FreshRSS no configurado, saltando...")
        return 0

    freshrss_selection = selection.get('freshrss', {})
    if not freshrss_selection:
        print("ℹ️  No hay artículos de FreshRSS seleccionados")
        return 0

    print("\n=== FRESHRSS ===")

    fr_config = config['freshrss']
    freshrss = FreshRSSClient(
        fr_config['url'],
        fr_config['username'],
        fr_config['password']
    )

    # Obtener todos los feeds para mapear IDs a nombres
    all_feeds = freshrss.list_feeds()
    feed_names = {feed['id']: feed['title'] for feed in all_feeds}

    processed = 0

    # Contar total de artículos
    total_articles = 0
    for category_feeds in freshrss_selection.get('categories', {}).values():
        for feed_articles in category_feeds.values():
            total_articles += len(feed_articles)

    print(f"📋 {total_articles} artículos seleccionados")

    article_count = 0

    # Procesar por categoría > feed > artículos
    for category_name, category_feeds in freshrss_selection.get('categories', {}).items():
        print(f"\n📁 Categoría: {category_name}")

        for feed_id, articles in category_feeds.items():
            feed_name = feed_names.get(feed_id, feed_id.split('/')[-1])

            print(f"\n  📰 Feed: {feed_name} ({len(articles)} artículos)")

            for article_info in articles:
                article_count += 1
                article_id = article_info.get('id')
                title = article_info.get('title', 'Sin título')

                # Opciones específicas del artículo
                article_options = {
                    'voice': article_info.get('voice', default_options['default_voice']),
                    'language': article_info.get('language', default_options['default_language']),
                    'include_youtube': article_info.get('include_youtube', default_options.get('include_youtube', False)),
                    'tts_engine': article_info.get('tts_engine', default_options.get('tts_engine', 'edge'))
                }

                print(f"\n  Procesando {article_count}/{total_articles}: {title}")
                print(f"    🎤 Voz: {article_options['voice']}")
                print(f"    🌍 Idioma: {article_options['language']}")
                if article_options['include_youtube']:
                    print(f"    📺 YouTube: Habilitado")

                try:
                    # Obtener artículo completo
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

                    # Crear convertidor con opciones del artículo
                    converter = ArticleToMP3Converter(
                        output_dir=default_options['output_dir'],
                        tts_engine=article_options['tts_engine'],
                        voice=article_options['voice'],
                        skip_existing=default_options.get('skip_existing', True),
                        target_language=article_options['language']
                    )

                    # Limpiar texto
                    text = converter.clean_text(content)

                    if text:
                        episode_title = f"[{category_name}] {feed_name} - {title}"

                        # Determinar si procesar con YouTube
                        if article_options['include_youtube']:
                            filepath = converter.process_and_convert_with_youtube(
                                text,
                                content,  # HTML original
                                episode_title,
                                original_language=fr_config.get('original-language'),
                                lang=article_options['language']
                            )
                        else:
                            filepath = converter.process_and_convert(
                                text,
                                episode_title,
                                original_language=fr_config.get('original-language'),
                                lang=article_options['language']
                            )

                        if filepath:
                            processed += 1
                            print(f"    ✓ Convertido: {os.path.basename(filepath)}")

                            if feed_generator:
                                feed_generator.add_episode(
                                    title=episode_title,
                                    filepath=filepath,
                                    description=f"{feed_name}: {title}",
                                    category=category_name
                                )

                except Exception as e:
                    print(f"    ✗ Error procesando artículo: {e}")

    print(f"\n✓ FreshRSS: {processed}/{total_articles} artículos procesados")
    return processed


def main():
    parser = argparse.ArgumentParser(
        description='Procesa artículos seleccionados con opciones personalizadas'
    )
    parser.add_argument('--selection', default='selection.json',
                       help='Archivo de selección JSON con opciones')
    parser.add_argument('--config', default='config.json',
                       help='Archivo de configuración JSON')
    parser.add_argument('--output', default='audio_articles',
                       help='Directorio de salida para los MP3')
    parser.add_argument('--generate-feed', action='store_true',
                       help='Generar/actualizar feed RSS/Podcast')
    parser.add_argument('--base-url', default='https://podcast.pollete.duckdns.org',
                       help='URL base para el feed RSS')

    args = parser.parse_args()

    # Cargar configuración
    config = load_config(args.config)
    if not config:
        return 1

    # Cargar selección
    selection = load_selection(args.selection)
    if not selection:
        return 1

    # Extraer opciones globales del selection.json
    global_options = selection.get('options', {})

    default_options = {
        'output_dir': args.output,
        'tts_engine': global_options.get('tts_engine', 'edge'),
        'default_voice': global_options.get('default_voice', 'es-ES-AlvaroNeural'),
        'default_language': global_options.get('default_language', 'es'),
        'include_youtube': global_options.get('include_youtube', False),
        'skip_existing': global_options.get('skip_existing', True),
        'generate_feed': args.generate_feed or global_options.get('generate_feed', True),
        'base_url': args.base_url,
        'feed_title': global_options.get('feed_title', 'Mis Artículos TTS'),
        'feed_description': global_options.get('feed_description', 'Artículos convertidos a audio')
    }

    print(f"""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   🎙️  Conversión de Artículos Seleccionados a MP3        ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝

⚙️  Opciones globales:
   🎤 Motor TTS: {default_options['tts_engine']}
   🔊 Voz por defecto: {default_options['default_voice']}
   🌍 Idioma por defecto: {default_options['default_language']}
   📺 YouTube: {'Habilitado' if default_options['include_youtube'] else 'Deshabilitado'} (por defecto)
   📂 Salida: {default_options['output_dir']}
   ⏭️  Omitir existentes: {'Sí' if default_options['skip_existing'] else 'No'}
    """)

    # Verificar edge-tts si es necesario
    if default_options['tts_engine'] == 'edge':
        try:
            import edge_tts
            print("✓ edge-tts disponible")
        except ImportError:
            print("⚠️  edge-tts no está instalado. Cambiando a gTTS...")
            default_options['tts_engine'] = 'gtts'

    # Inicializar generador de feed si se solicita
    feed_generator = None
    if default_options['generate_feed']:
        feed_generator = PodcastFeedGenerator(
            output_dir=default_options['output_dir'],
            base_url=default_options['base_url'],
            title=default_options['feed_title'],
            description=default_options['feed_description']
        )
        print("✓ Generador de feed RSS habilitado")

    # Procesar artículos
    total_processed = 0

    # Wallabag
    wb_processed = process_wallabag_articles(selection, config, default_options, feed_generator)
    total_processed += wb_processed

    # FreshRSS
    fr_processed = process_freshrss_articles(selection, config, default_options, feed_generator)
    total_processed += fr_processed

    # Resumen
    print(f"""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   ✅ Proceso Completado                                   ║
║                                                           ║
║   📊 {total_processed} artículos convertidos exitosamente           ║
║   📂 Archivos guardados en: {default_options['output_dir']:<25} ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
    """)

    # Generar/actualizar feed RSS
    if default_options['generate_feed']:
        print("\n🎙️  Generando/actualizando feed RSS para podcast...")

        if feed_generator and feed_generator.episodes:
            # Generar feed desde los nuevos episodios
            feed_path = feed_generator.generate_rss()
            print(f"✓ Feed RSS actualizado: {feed_path}")
        else:
            # Si no hay nuevos episodios pero queremos actualizar el feed
            # Generar desde todos los archivos MP3 existentes
            feed_dir = os.path.dirname(default_options['output_dir']) or '.'
            success = generate_feed_from_existing_files(
                output_dir=default_options['output_dir'],
                base_url=default_options['base_url'],
                feed_title=default_options['feed_title'],
                feed_description=default_options['feed_description'],
                feed_dir=feed_dir
            )
            if success:
                print(f"✓ Feed RSS generado desde archivos existentes")

    return 0


if __name__ == "__main__":
    sys.exit(main())
