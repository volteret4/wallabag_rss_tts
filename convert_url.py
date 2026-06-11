#!/usr/bin/env python3
"""
Convert an arbitrary article URL to MP3 and add it to the podcast feed.
Usage: python3 convert_url.py --url https://... [--voice ...] [--language auto|es|en] [--include-youtube] [--title ...]
"""

import argparse
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

try:
    from articles_to_mp3 import ArticleToMP3Converter, generate_feed_from_existing_files
except ImportError:
    print("✗ Error: No se puede importar articles_to_mp3.py")
    sys.exit(1)


def extract_article(url: str) -> tuple:
    """Fetch URL and return (title, html_content)."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0'
    }
    resp = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, 'html.parser')

    for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form', 'iframe']):
        tag.decompose()

    # Title: prefer <h1>, fall back to <title>
    title = ''
    h1 = soup.find('h1')
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        t = soup.find('title')
        if t:
            title = t.get_text(strip=True)

    # Content: try common article containers in order
    content_el = None
    for selector in [
        'article', '[role="main"]', 'main',
        '.article-body', '.article-content', '.post-content',
        '.entry-content', '.content', '#content', '#main',
    ]:
        content_el = soup.select_one(selector)
        if content_el:
            break

    if not content_el:
        content_el = soup.find('body') or soup

    return title, str(content_el)


def main():
    parser = argparse.ArgumentParser(description='Convierte una URL de artículo a MP3')
    parser.add_argument('--url', required=True, help='URL del artículo')
    parser.add_argument('--voice', default='es-ES-AlvaroNeural')
    parser.add_argument('--language', default='auto',
                        help='Idioma del texto: auto, es, en, fr, … (auto = detección automática)')
    parser.add_argument('--include-youtube', action='store_true',
                        help='Incluir audio de vídeos de YouTube embebidos')
    parser.add_argument('--title', default='', help='Título personalizado (opcional)')
    parser.add_argument('--output', default='audio_articles', help='Directorio de salida MP3')
    parser.add_argument('--base-url', default='https://podcast.pollete.duckdns.org')
    args = parser.parse_args()

    print(f"🌐 Obteniendo artículo: {args.url}")
    try:
        page_title, html_content = extract_article(args.url)
    except Exception as e:
        print(f"✗ Error al obtener la URL: {e}")
        sys.exit(1)

    title = args.title or page_title or args.url
    print(f"📄 Título: {title}")

    # Detect or resolve target language before creating the converter
    # (we need a temporary instance just for language detection)
    _tmp = ArticleToMP3Converter(output_dir=args.output, tts_engine='edge', voice=args.voice, skip_existing=False)
    raw_text = _tmp.clean_text(html_content)

    lang = args.language
    if lang == 'auto':
        detected = _tmp.detect_language(raw_text)
        lang = detected if detected else 'es'
        print(f"🔍 Idioma detectado: {lang}")
        target_language = None  # no translation needed, already in detected lang
    else:
        target_language = lang  # converter will auto-detect source and translate if different

    # Strip bare URLs from plain text (not link labels, just raw https://... strings)
    text = re.sub(r'https?://\S+|www\.\S+', ' ', raw_text)
    text = re.sub(r'\s+', ' ', text).strip()

    if not text or len(text.split()) < 20:
        print("✗ No se pudo extraer texto suficiente del artículo")
        sys.exit(1)

    converter = ArticleToMP3Converter(
        output_dir=args.output,
        tts_engine='edge',
        voice=args.voice,
        skip_existing=False,
        target_language=target_language,
    )

    print(f"\nProcesando 1/1: {title}")
    print(f"  🎤 Voz: {args.voice} | Idioma: {lang} | YouTube: {'Sí' if args.include_youtube else 'No'}")

    try:
        if args.include_youtube:
            filepath = converter.process_and_convert_with_youtube(
                text, html_content, title, lang=lang
            )
        else:
            filepath = converter.process_and_convert(text, title, lang=lang)
    except Exception as e:
        print(f"✗ Error en conversión TTS: {e}")
        sys.exit(1)

    if not filepath:
        print("✗ No se generó el archivo MP3")
        sys.exit(1)

    print(f"✓ MP3 creado: {os.path.basename(filepath)}")

    # Regenerate podcast feed
    print("\n🎙 Actualizando feed RSS...")
    feed_dir = os.path.dirname(os.path.abspath(args.output)) or '.'
    generate_feed_from_existing_files(
        output_dir=args.output,
        base_url=args.base_url,
        feed_title='Mis Artículos TTS',
        feed_description='Artículos convertidos a audio',
        feed_dir=feed_dir,
    )
    print("✓ Listo")


if __name__ == '__main__':
    main()
