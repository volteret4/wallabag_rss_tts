#!/usr/bin/env python3
"""
Script mejorado para convertir artÃƒÂ­culos de Wallabag y FreshRSS a MP3 usando TTS
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
import glob
import shutil
import tempfile
import subprocess
import asyncio
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom



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

        # Ejecutar ffmpeg (capturando stderr solo para errores)
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True
        )

        # Limpiar archivo temporal
        try:
            os.unlink(list_file)
        except:
            pass

        if result.returncode == 0:
            print(f"  âœ“ Audios combinados exitosamente")
            return True
        else:
            print(f"  âœ— Error combinando audios con ffmpeg (cÃ³digo: {result.returncode})")
            if result.stderr:
                # Mostrar solo las Ãºltimas lÃ­neas del error
                error_lines = result.stderr.strip().split('\n')
                if error_lines:
                    print(f"     Ãšltimo error: {error_lines[-1][:100]}")
            return False

    except Exception as e:
        print(f"  âœ— Error al combinar audios: {e}")
        return False



def add_chapters_to_mp3(mp3_file, chapters):
    """
    AÃ±ade capÃ­tulos a un archivo MP3 usando mutagen

    Args:
        mp3_file: Ruta al archivo MP3
        chapters: Lista de diccionarios con 'title', 'start_time' (en milisegundos)
                 Ejemplo: [
                     {'title': 'Texto del artÃ­culo', 'start_time': 0},
                     {'title': 'Video 1', 'start_time': 180000},  # 3 minutos
                 ]

    Returns:
        bool: True si tuvo Ã©xito, False si fallÃ³
    """
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, CTOC, CHAP, TIT2, CTOCFlags

        # Cargar archivo MP3
        audio = MP3(mp3_file, ID3=ID3)

        # Asegurarse de que hay tags ID3
        if audio.tags is None:
            audio.add_tags()

        # Limpiar capÃ­tulos existentes si los hay
        for key in list(audio.tags.keys()):
            if key.startswith('CHAP') or key.startswith('CTOC'):
                del audio.tags[key]

        # Obtener duraciÃ³n total del archivo en milisegundos
        total_duration_ms = int(audio.info.length * 1000)

        # Crear frames de capÃ­tulos
        chapter_ids = []
        for i, chapter in enumerate(chapters):
            chapter_id = f"chp{i}"
            chapter_ids.append(chapter_id)

            start_time = chapter['start_time']
            # El final es el inicio del siguiente capÃ­tulo, o el final del archivo
            if i < len(chapters) - 1:
                end_time = chapters[i + 1]['start_time']
            else:
                end_time = total_duration_ms

            # Crear frame CHAP
            chap = CHAP(
                encoding=3,  # UTF-8
                element_id=chapter_id,
                start_time=start_time,
                end_time=end_time,
                start_offset=0xFFFFFFFF,  # No se usa
                end_offset=0xFFFFFFFF,    # No se usa
                sub_frames=[
                    TIT2(encoding=3, text=chapter['title'])
                ]
            )
            audio.tags.add(chap)

        # Crear tabla de contenidos (CTOC) que agrupa todos los capÃ­tulos
        ctoc = CTOC(
            encoding=3,
            element_id='toc',
            flags=CTOCFlags.TOP_LEVEL | CTOCFlags.ORDERED,
            child_element_ids=chapter_ids,
            sub_frames=[
                TIT2(encoding=3, text='Contenido')
            ]
        )
        audio.tags.add(ctoc)

        # Guardar cambios
        audio.save()

        print(f"  âœ“ {len(chapters)} capÃ­tulos aÃ±adidos al archivo MP3")
        return True

    except Exception as e:
        print(f"  âš ï¸  Error al aÃ±adir capÃ­tulos: {e}")
        print(f"     (El archivo MP3 se creÃ³ correctamente, solo sin capÃ­tulos)")
        return False


def get_audio_duration_ms(filepath):
    """
    Obtiene la duraciÃ³n de un archivo de audio en milisegundos

    Args:
        filepath: Ruta al archivo de audio

    Returns:
        int: DuraciÃ³n en milisegundos, o 0 si falla
    """
    try:
        from mutagen.mp3 import MP3
        audio = MP3(filepath)
        return int(audio.info.length * 1000)
    except:
        # Fallback: estimaciÃ³n basada en tamaÃ±o de archivo
        # 1 MB â‰ˆ 60 segundos para MP3 a 128kbps
        try:
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            return int(size_mb * 60 * 1000)
        except:
            return 0


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
            # Usar solo los primeros 1000 caracteres para detecciÃƒÂ³n mÃƒÂ¡s rÃƒÂ¡pida
            sample = text[:1000] if len(text) > 1000 else text
            detected = detect(sample)
            return detected
        except Exception as e:
            print(f"Ã¢Å¡Â  Error al detectar idioma: {e}")
            return None

    def translate_text(self, text, source_lang, target_lang):
        """Traduce el texto del idioma origen al idioma destino"""
        try:
            from deep_translator import GoogleTranslator

            print(f"Ã°Å¸â€â€ž Traduciendo de {source_lang} a {target_lang}...")

            # LÃƒÂ­mite de 4900 caracteres por consulta (margen de seguridad)
            max_length_per_chunk = 4900
            max_chunks = 4  # Hasta 4 consultas
            max_total_length = max_length_per_chunk * max_chunks  # 19600 caracteres mÃƒÂ¡ximo

            original_length = len(text)

            # Si el texto es muy largo, truncar
            if original_length > max_total_length:
                print(f"Ã¢Å¡Â  Texto muy largo ({original_length} caracteres), truncando a {max_total_length}...")
                text = text[:max_total_length]
                original_length = len(text)

            # Calcular nÃƒÂºmero de chunks necesarios
            num_chunks = (original_length + max_length_per_chunk - 1) // max_length_per_chunk

            translator = GoogleTranslator(source=source_lang, target=target_lang)

            # Si cabe en una sola consulta
            if num_chunks == 1:
                print(f"Ã°Å¸â€œÂ Traduciendo en 1 consulta ({original_length} caracteres)...")
                translated = translator.translate(text)
                print(f"Ã¢Å“â€œ TraducciÃƒÂ³n completada ({len(translated)} caracteres)")
                return translated

            # Si necesita mÃƒÂºltiples consultas
            else:
                print(f"Ã°Å¸â€œÂ Traduciendo en {num_chunks} consultas ({original_length} caracteres totales)...")

                chunks = []
                chunk_size = original_length // num_chunks

                # Dividir el texto en chunks
                for i in range(num_chunks):
                    if i == num_chunks - 1:
                        # ÃƒÅ¡ltimo chunk: tomar todo lo que queda
                        chunk_start = i * chunk_size
                        chunk = text[chunk_start:].strip()
                    else:
                        # Buscar punto de corte natural
                        chunk_start = i * chunk_size
                        chunk_end = (i + 1) * chunk_size

                        # Buscar un buen punto de corte (espacio, salto de lÃƒÂ­nea o punto)
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

                print(f"Ã¢Å“â€œ TraducciÃƒÂ³n completada ({len(translated)} caracteres)")
                return translated

        except Exception as e:
            print(f"Ã¢Å“â€” Error al traducir: {e}")
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
        """Convierte un tÃƒÂ­tulo en un nombre de archivo vÃƒÂ¡lido"""
        # Eliminar caracteres no vÃƒÂ¡lidos
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
            print(f"Ã¢Å“â€” Error con edge-tts: {e}")
            return False

    def text_to_mp3_gtts(self, text, filepath, lang='es'):
        """Convierte texto a MP3 usando gTTS (Google TTS)"""
        try:
            tts = gTTS(text=text, lang=lang, slow=False)
            tts.save(filepath)
            return True
        except Exception as e:
            print(f"Ã¢Å“â€” Error con gTTS: {e}")
            return False

    def process_and_convert(self, text, title, original_language=None, lang='es'):
        """
        Procesa el texto (detecta idioma, traduce si es necesario) y lo convierte a MP3

        Args:
            text: Texto a convertir
            title: TÃƒÂ­tulo del artÃƒÂ­culo
            original_language: Idioma original especificado en config (opcional)
            lang: Idioma para gTTS
        """
        # Detectar idioma si no se especificÃƒÂ³
        if self.target_language:
            detected_lang = original_language or self.detect_language(text)

            if detected_lang:
                print(f"Ã°Å¸â€œÂ Idioma detectado: {detected_lang}")

                # Normalizar cÃƒÂ³digos de idioma (en-us -> en, es-es -> es, etc.)
                detected_lang_short = detected_lang.split('-')[0].lower()
                target_lang_short = self.target_language.split('-')[0].lower()

                # Traducir si es necesario
                if detected_lang_short != target_lang_short:
                    print(f"Ã°Å¸Å’Â TraducciÃƒÂ³n necesaria: {detected_lang_short} Ã¢â€ â€™ {target_lang_short}")
                    text = self.translate_text(text, detected_lang_short, target_lang_short)
                else:
                    print(f"Ã¢Å“â€œ Sin traducciÃƒÂ³n necesaria (ya estÃƒÂ¡ en {target_lang_short})")

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
                    print(f"Ã¢Å â„¢ Ya existe (omitiendo): {filename}.mp3")
                    return filepath
                else:
                    # Si no se quiere omitir, crear con timestamp
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filepath = os.path.join(self.output_dir, f"{filename}_{timestamp}.mp3")
                    print(f"Ã¢Å¡Â  Archivo existe, creando nueva versiÃƒÂ³n: {filename}_{timestamp}.mp3")

            print(f"Generando audio ({self.tts_engine}): {filename}.mp3")

            success = False
            if self.tts_engine == "edge":
                # edge-tts es asÃƒÂ­ncrono, usar asyncio
                success = asyncio.run(self.text_to_mp3_edge(text, filepath))
            elif self.tts_engine == "gtts":
                success = self.text_to_mp3_gtts(text, filepath, lang)

            if success:
                print(f"Ã¢Å“â€œ Guardado: {filepath}")
                return filepath
            else:
                print(f"Ã¢Å“â€” Error al generar audio para '{title}'")
                return None

        except Exception as e:
            print(f"Ã¢Å“â€” Error al generar audio para '{title}': {e}")
            return None



    def process_and_convert_with_youtube(self, text, html_content, title, original_language=None, lang='es'):
        """
        Procesa artÃ­culo con texto y videos de YouTube, creando un MP3 combinado

        Args:
            text: Texto limpio del artÃ­culo (ya procesado con clean_text)
            html_content: Contenido HTML original (para extraer URLs de YouTube)
            title: TÃ­tulo del artÃ­culo
            original_language: Idioma original especificado en config (opcional)
            lang: Idioma para gTTS

        Returns:
            str: Ruta al archivo MP3 final, o None si falla
        """
        print(f"\nðŸŽ¬ Procesando artÃ­culo con contenido de YouTube: {title}")

        # 1. Extraer URLs de YouTube
        youtube_urls = extract_youtube_urls(html_content)

        if not youtube_urls:
            print(f"  â„¹ï¸  No se encontraron videos de YouTube, procesando como artÃ­culo normal")
            return self.process_and_convert(text, title, original_language, lang)

        print(f"  ðŸ“º Encontrados {len(youtube_urls)} videos de YouTube")
        for i, url in enumerate(youtube_urls, 1):
            print(f"    {i}. {url}")

        # Crear directorio temporal para archivos intermedios
        temp_dir = tempfile.mkdtemp(prefix="article_youtube_")
        audio_parts = []

        try:
            # 2. Generar TTS del texto
            print(f"  ðŸ”Š Generando audio del texto...")

            # Detectar idioma y traducir si es necesario
            if self.target_language:
                detected_lang = original_language or self.detect_language(text)
                if detected_lang:
                    detected_lang_short = detected_lang.split('-')[0].lower()
                    target_lang_short = self.target_language.split('-')[0].lower()

                    if detected_lang_short != target_lang_short:
                        text = self.translate_text(text, detected_lang_short, target_lang_short)

            # Generar audio del texto
            tts_file = os.path.join(temp_dir, "tts_text.mp3")

            success = False
            if self.tts_engine == "edge":
                import asyncio
                success = asyncio.run(self.text_to_mp3_edge(text, tts_file))
            elif self.tts_engine == "gtts":
                success = self.text_to_mp3_gtts(text, tts_file, lang)

            if success and os.path.exists(tts_file):
                audio_parts.append(tts_file)
                print(f"  âœ“ Audio del texto generado")
            else:
                print(f"  âœ— Error al generar audio del texto")

            # 3. Descargar audio de videos de YouTube
            print(f"  ðŸ“¥ Descargando audio de videos de YouTube...")
            for i, url in enumerate(youtube_urls, 1):
                print(f"    Descargando video {i}/{len(youtube_urls)}...")
                yt_audio = download_youtube_audio(url, temp_dir, f"yt_{i}")
                if yt_audio and os.path.exists(yt_audio):
                    audio_parts.append(yt_audio)
                else:
                    print(f"    âš ï¸  No se pudo descargar el audio del video {i}")

            if len(audio_parts) == 0:
                print(f"  âœ— No se generÃ³ ningÃºn audio")
                return None

            # 4. Preparar informaciÃ³n de capÃ­tulos
            print(f"  ðŸ“‘ Preparando informaciÃ³n de capÃ­tulos...")
            chapters = []
            current_time_ms = 0

            # CapÃ­tulo 1: Texto del artÃ­culo
            chapters.append({
                'title': 'Texto del artÃ­culo',
                'start_time': current_time_ms
            })

            # Obtener duraciÃ³n del audio TTS
            if len(audio_parts) > 0:
                tts_duration_ms = get_audio_duration_ms(audio_parts[0])
                current_time_ms += tts_duration_ms

            # CapÃ­tulos para cada video de YouTube
            for i in range(1, len(audio_parts)):
                video_num = i
                chapters.append({
                    'title': f'Video {video_num}',
                    'start_time': current_time_ms
                })

                # Obtener duraciÃ³n de este video
                video_duration_ms = get_audio_duration_ms(audio_parts[i])
                current_time_ms += video_duration_ms

            # 5. Combinar todos los audios
            print(f"  ðŸ”— Combinando {len(audio_parts)} archivos de audio...")

            # Crear nombre de archivo final
            filename = self.sanitize_filename(title)
            filepath = os.path.join(self.output_dir, f"{filename}.mp3")

            # Comprobar si el archivo ya existe
            if os.path.exists(filepath):
                if self.skip_existing:
                    print(f"  âŠ™ Ya existe (omitiendo): {filename}.mp3")
                    return filepath
                else:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filepath = os.path.join(self.output_dir, f"{filename}_{timestamp}.mp3")

            # Combinar archivos
            if combine_audio_files(audio_parts, filepath):
                print(f"  âœ“ Archivo final creado: {os.path.basename(filepath)}")
                print(f"  ðŸ“Š Componentes: 1 TTS + {len(youtube_urls)} video(s) de YouTube")

                # 6. AÃ±adir capÃ­tulos al archivo MP3
                if len(chapters) > 1:
                    print(f"  ðŸ“– AÃ±adiendo {len(chapters)} capÃ­tulos al MP3...")
                    add_chapters_to_mp3(filepath, chapters)

                return filepath
            else:
                print(f"  âœ— Error al combinar archivos de audio")
                return None

        except Exception as e:
            print(f"  âœ— Error procesando artÃ­culo con YouTube: {e}")
            return None

        finally:
            # Limpiar archivos temporales
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except:
                pass


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
            print("Ã¢Å“â€œ Autenticado en Wallabag")
            return True
        except Exception as e:
            print(f"Ã¢Å“â€” Error de autenticaciÃƒÂ³n en Wallabag: {e}")
            return False

    def get_articles(self, archive=0, limit=10):
        """Obtiene artÃƒÂ­culos de Wallabag"""
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
            print(f"Ã¢Å“â€œ Obtenidos {len(articles)} artÃƒÂ­culos de Wallabag")
            return articles
        except Exception as e:
            print(f"Ã¢Å“â€” Error al obtener artÃƒÂ­culos de Wallabag: {e}")
            return []



    def get_article(self, article_id):
        """Obtiene un artÃ­culo especÃ­fico de Wallabag"""
        if not self.token:
            if not self.authenticate():
                return None

        headers = {'Authorization': f'Bearer {self.token}'}

        try:
            response = requests.get(
                f"{self.url}/api/entries/{article_id}.json",
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"âœ— Error al obtener artÃ­culo {article_id}: {e}")
            return None

    def mark_as_read(self, article_id):
        """Marca un artÃ­culo como leÃ­do (archivado) en Wallabag"""
        if not self.token:
            if not self.authenticate():
                return False

        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }

        # En Wallabag, marcar como leÃ­do = archivar el artÃ­culo
        data = {'archive': 1}

        try:
            response = requests.patch(
                f"{self.url}/api/entries/{article_id}.json",
                headers=headers,
                json=data
            )
            response.raise_for_status()

            # Verificar respuesta
            result = response.json()
            if result.get('is_archived') == 1 or result.get('is_archived') == True:
                print(f"  âœ“ Marcado como leÃ­do en Wallabag (ID: {article_id})")
                return True
            else:
                print(f"  âš ï¸  Respuesta inesperada al marcar como leÃ­do")
                return False

        except Exception as e:
            print(f"  âœ— Error al marcar como leÃ­do (ID: {article_id}): {e}")
            return False


class FreshRSSClient:
    def __init__(self, url, username, password):
        self.url = url.rstrip('/')
        self.username = username
        self.password = password
        self.auth_token = None

    def authenticate(self):
        """AutenticaciÃƒÂ³n usando Google Reader API de FreshRSS"""
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
                    print(f"Ã¢Å“â€œ Autenticado en FreshRSS")
                    return True

            print("Ã¢Å“â€” No se encontrÃƒÂ³ el token de autenticaciÃƒÂ³n")
            return False

        except Exception as e:
            print(f"Ã¢Å“â€” Error de autenticaciÃƒÂ³n en FreshRSS: {e}")
            return False

    def list_categories(self):
        """Lista todas las categorÃƒÂ­as/tags disponibles"""
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
                # Filtrar solo las categorÃƒÂ­as (labels)
                if '/label/' in tag_id:
                    category_name = tag_id.split('/label/')[-1]
                    categories.append({
                        'id': tag_id,
                        'name': category_name
                    })

            return categories
        except Exception as e:
            print(f"Ã¢Å“â€” Error al listar categorÃƒÂ­as: {e}")
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
            print(f"Ã¢Å“â€” Error al listar feeds: {e}")
            return []

    def get_articles(self, stream_id=None, limit=10, unread_only=True):
        """
        Obtiene artÃƒÂ­culos de FreshRSS

        stream_id puede ser:
        - None o 'reading-list': todos los artÃƒÂ­culos
        - 'user/-/label/CATEGORIA': artÃƒÂ­culos de una categorÃƒÂ­a
        - 'feed/FEED_ID': artÃƒÂ­culos de un feed especÃƒÂ­fico
        """
        if not self.auth_token:
            if not self.authenticate():
                return []

        # Construir URL del stream
        if stream_id:
            if stream_id == 'reading-list':
                stream_path = 'reading-list'
            elif stream_id.startswith('user/-/label/'):
                # CategorÃƒÂ­a especÃƒÂ­fica
                stream_path = f"contents/{stream_id}"
            elif stream_id.startswith('feed/'):
                # Feed especÃƒÂ­fico
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
            print(f"Ã¢Å“â€” Error al obtener artÃƒÂ­culos: {e}")
            return []

    def mark_as_read(self, article_id):
        """Marca un artÃ­culo como leÃ­do en FreshRSS"""
        if not self.auth_token:
            if not self.authenticate():
                return False

        url = f"{self.url}/api/greader.php/reader/api/0/edit-tag"
        headers = {
            'Authorization': f'GoogleLogin auth={self.auth_token}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        # FreshRSS usa la API de Google Reader
        data = {
            'i': article_id,
            'a': 'user/-/state/com.google/read',
            'ac': 'edit'
        }

        try:
            response = requests.post(url, headers=headers, data=data)
            response.raise_for_status()

            # La API de Google Reader devuelve "OK" en texto plano si tuvo Ã©xito
            if response.text.strip().upper() == 'OK':
                print(f"  âœ“ Marcado como leÃ­do en FreshRSS (ID: {article_id})")
                return True
            else:
                print(f"  âš ï¸  Respuesta inesperada de FreshRSS: {response.text[:100]}")
                # AÃºn asÃ­ considerarlo exitoso si no hubo error HTTP
                return True

        except requests.exceptions.HTTPError as e:
            print(f"  âœ— Error HTTP al marcar como leÃ­do en FreshRSS: {e}")
            print(f"     Respuesta del servidor: {e.response.text[:200] if e.response else 'N/A'}")
            return False
        except Exception as e:
            print(f"  âœ— Error al marcar como leÃ­do en FreshRSS: {e}")
            return False



class PodcastFeedGenerator:
    """Genera un feed RSS/Podcast simple"""

    def __init__(self, output_dir, base_url, title="Mis ArtÃƒÂ­culos TTS", description="ArtÃƒÂ­culos convertidos a audio", image_url=None, author=None, feed_dir=None):
        self.output_dir = output_dir
        self.feed_dir = feed_dir if feed_dir is not None else os.path.dirname(output_dir) if output_dir != '.' else '.'
        self.base_url = base_url.rstrip('/')
        self.title = title
        self.description = description
        self.image_url = image_url
        self.author = author
        self.episodes = []

    def get_file_size(self, filepath):
        """Obtiene el tamaÃƒÂ±o del archivo en bytes"""
        try:
            return os.path.getsize(filepath)
        except:
            return 0

    def get_audio_duration(self, filepath):
        """Intenta obtener la duraciÃƒÂ³n del audio"""
        try:
            from mutagen.mp3 import MP3
            audio = MP3(filepath)
            return int(audio.info.length)
        except:
            # EstimaciÃƒÂ³n basada en tamaÃƒÂ±o (1 MB Ã¢â€°Ë† 60 segundos)
            size_mb = self.get_file_size(filepath) / (1024 * 1024)
            return int(size_mb * 60)

    def add_episode(self, title, filepath, description="", category=""):
        """AÃƒÂ±ade un episodio al feed"""
        if not os.path.exists(filepath):
            return

        filename = os.path.basename(filepath)
        # La URL debe incluir el subdirectorio donde están los MP3
        # Si output_dir es "audio_articles", la URL será /audio_articles/filename.mp3
        dir_name = os.path.basename(os.path.normpath(self.output_dir))
        url = f"{self.base_url}/{dir_name}/{filename}"

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

        # AÃƒÂ±adir autor si estÃƒÂ¡ disponible
        if self.author:
            SubElement(channel, 'itunes:author').text = self.author

        # AÃƒÂ±adir imagen si estÃƒÂ¡ disponible
        if self.image_url:
            SubElement(channel, 'itunes:image', {'href': self.image_url})
            image_elem = SubElement(channel, 'image')
            SubElement(image_elem, 'url').text = self.image_url
            SubElement(image_elem, 'title').text = self.title
            SubElement(image_elem, 'link').text = self.base_url

        # Ordenar episodios por fecha (mÃƒÂ¡s reciente primero)
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

        output_path = os.path.join(self.feed_dir, output_file)
        os.makedirs(self.feed_dir, exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(xml_str)

        print(f"\nÃ¢Å“â€œ Feed RSS generado: {output_path}")
        print(f"Ã¢Å“â€œ URL del feed: {self.base_url}/{output_file}")
        print(f"Ã¢Å“â€œ Episodios: {len(self.episodes)}")

        return output_path




def generate_feed_from_existing_files(output_dir, base_url, feed_title, feed_description, feed_dir=None):
    """Genera feed RSS desde archivos MP3 existentes"""
    import glob

    if not os.path.exists(output_dir):
        print(f"✗ El directorio {output_dir} no existe")
        return False

    mp3_files = glob.glob(os.path.join(output_dir, "*.mp3"))

    if not mp3_files:
        print(f"✗ No se encontraron archivos MP3 en {output_dir}")
        return False

    print(f"\n📁 Directorio: {output_dir}")
    print(f"✓ Encontrados {len(mp3_files)} archivos MP3")

    feed_generator = PodcastFeedGenerator(
        output_dir=output_dir,
        base_url=base_url,
        title=feed_title,
        description=feed_description,
        feed_dir=feed_dir
    )

    print(f"\n📝 Agregando episodios al feed...")
    for mp3_file in sorted(mp3_files, key=lambda x: os.path.getmtime(x), reverse=True):
        filename = os.path.basename(mp3_file)
        title = os.path.splitext(filename)[0]

        category = ""
        if title.startswith('[') and ']' in title:
            category_end = title.index(']')
            category = title[1:category_end]
            title_clean = title[category_end+1:].strip()
            if title_clean.startswith('- '):
                title_clean = title_clean[2:]
        else:
            title_clean = title

        print(f"  + {filename}")

        feed_generator.add_episode(
            title=title,
            filepath=mp3_file,
            description=title_clean,
            category=category
        )

    print(f"\n🎙️  Generando feed RSS...")
    feed_generator.generate_rss()
    return True


def print_available_voices():
    """Muestra las voces disponibles para edge-tts"""
    try:
        import edge_tts
        print("\n=== Voces disponibles para edge-tts ===")
        print("\nEspaÃƒÂ±ol:")
        spanish_voices = [
            "es-ES-AlvaroNeural (Hombre, EspaÃƒÂ±a)",
            "es-ES-ElviraNeural (Mujer, EspaÃƒÂ±a)",
            "es-ES-AbrilNeural (Mujer, EspaÃƒÂ±a)",
            "es-MX-DaliaNeural (Mujer, MÃƒÂ©xico)",
            "es-MX-JorgeNeural (Hombre, MÃƒÂ©xico)",
            "es-AR-ElenaNeural (Mujer, Argentina)",
            "es-AR-TomasNeural (Hombre, Argentina)",
        ]
        for voice in spanish_voices:
            print(f"  - {voice}")

        print("\nInglÃƒÂ©s:")
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
        print("edge-tts no estÃƒÂ¡ instalado. InstÃƒÂ¡lalo con: pip install edge-tts")


def main():
    parser = argparse.ArgumentParser(
        description='Convierte artÃƒÂ­culos de Wallabag y FreshRSS a MP3 con TTS mejorado',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  # Usar edge-tts (mejor calidad)
  python3 articles_to_mp3.py --tts edge

  # Usar edge-tts con voz especÃƒÂ­fica
  python3 articles_to_mp3.py --tts edge --voice es-ES-ElviraNeural

  # Traducir al espaÃƒÂ±ol automÃƒÂ¡ticamente
  python3 articles_to_mp3.py --language es

  # No omitir archivos existentes
  python3 articles_to_mp3.py --no-skip-existing

  # Ver voces disponibles
  python3 articles_to_mp3.py --list-voices

  # Listar categorÃƒÂ­as y feeds de FreshRSS
  python3 articles_to_mp3.py --freshrss-list
        """
    )

    parser.add_argument('--config', default='config.json',
                       help='Archivo de configuraciÃƒÂ³n JSON')
    parser.add_argument('--output', default='audio_articles',
                       help='Directorio de salida para los MP3')
    parser.add_argument('--limit', type=int, default=10,
                       help='NÃƒÂºmero mÃƒÂ¡ximo de artÃƒÂ­culos (si no se especifica en config)')
    parser.add_argument('--lang', default='es',
                       help='Idioma para gTTS (es, en, fr, etc.)')
    parser.add_argument('--source', choices=['wallabag', 'freshrss', 'both'],
                       default='both', help='Fuente de artÃƒÂ­culos')
    parser.add_argument('--tts', choices=['gtts', 'edge'],
                       default='gtts', help='Motor TTS a usar (gtts = estable, edge = mejor calidad)')
    parser.add_argument('--voice', default='es-ES-AlvaroNeural',
                       help='Voz para edge-tts (ej: es-ES-ElviraNeural)')
    parser.add_argument('--skip-existing', dest='skip_existing', action='store_true',
                       help='Omitir archivos que ya existen (por defecto)')
    parser.add_argument('--no-skip-existing', dest='skip_existing', action='store_false',
                       help='No omitir archivos existentes, crear versiones con timestamp')
    parser.add_argument('--language', choices=['es', 'en', 'fr', 'de', 'it', 'pt'],
                       help='Idioma destino para traducciÃƒÂ³n automÃƒÂ¡tica (es, en, fr, de, it, pt). Si se especifica, se detectarÃƒÂ¡ el idioma del artÃƒÂ­culo y se traducirÃƒÂ¡ si es necesario')
    parser.add_argument('--list-voices', action='store_true',
                       help='Muestra las voces disponibles para edge-tts')
    parser.add_argument('--freshrss-list', action='store_true',
                       help='Lista categorÃƒÂ­as y feeds de FreshRSS')
    parser.add_argument('--generate-feed', action='store_true',
                       help='Generar feed RSS/Podcast')
    parser.add_argument('--base-url', default='https://podcast.pollete.duckdns.org',
                       help='URL base para el feed RSS')
    parser.add_argument('--feed-title', default='Mis ArtÃƒÂ­culos TTS',
                       help='TÃƒÂ­tulo del podcast')
    parser.add_argument('--feed-description', default='ArtÃƒÂ­culos convertidos a audio',
                       help='DescripciÃƒÂ³n del podcast')

    parser.add_argument('--mark-as-read', action='store_true',
                       help='Marcar artÃ­culos como leÃ­dos despuÃ©s de procesarlos')
    parser.add_argument('--only-xml', action='store_true',
                       help='Solo generar podcast.xml desde archivos MP3 existentes')

    parser.set_defaults(skip_existing=True)

    args = parser.parse_args()


    # Verificar dependencias para YouTube si hay feeds configurados con include_youtube
    needs_youtube_deps = False
    if os.path.exists(args.config):
        with open(args.config, 'r') as f:
            config_preview = json.load(f)

        # Verificar si hay feeds o categorÃ­as con include_youtube
        if 'freshrss' in config_preview:
            for feed in config_preview['freshrss'].get('feeds', []):
                if feed.get('include_youtube', False):
                    needs_youtube_deps = True
                    break

            if not needs_youtube_deps:
                for cat in config_preview['freshrss'].get('categories', []):
                    if cat.get('include_youtube', False):
                        needs_youtube_deps = True
                        break

        # Si se necesitan dependencias de YouTube, verificarlas
        if needs_youtube_deps:
            yt_dlp_ok, ffmpeg_ok = check_dependencies()

            if not yt_dlp_ok or not ffmpeg_ok:
                print("\nâš ï¸  ADVERTENCIA: Funcionalidad de YouTube habilitada pero faltan dependencias:")
                if not yt_dlp_ok:
                    print("  âœ— yt-dlp no estÃ¡ instalado")
                    print("    Instala con: pip install yt-dlp --break-system-packages")
                    print("    O en Ubuntu: sudo apt install yt-dlp")
                if not ffmpeg_ok:
                    print("  âœ— ffmpeg no estÃ¡ instalado")
                    print("    Instala con: sudo apt install ffmpeg")
                print("\n  Los artÃ­culos con videos de YouTube se procesarÃ¡n sin el audio de los videos.\n")

    # Mostrar voces disponibles
    if args.list_voices:
        print_available_voices()
        return

    # Cargar configuraciÃƒÂ³n
    if not os.path.exists(args.config):
        print(f"Ã¢Å“â€” No se encuentra el archivo de configuraciÃƒÂ³n: {args.config}")
        print("\nCrea un archivo config.json. Ver config.json.example para la estructura.")
        return

    with open(args.config, 'r') as f:
        config = json.load(f)

    # Listar categorÃƒÂ­as y feeds de FreshRSS
    if args.freshrss_list:
        if 'freshrss' not in config:
            print("Ã¢Å“â€” No hay configuraciÃƒÂ³n de FreshRSS en config.json")
            return

        fr_config = config['freshrss']
        freshrss = FreshRSSClient(
            fr_config['url'],
            fr_config['username'],
            fr_config['password']
        )

        print("\n=== CATEGORÃƒÂAS ===")
        categories = freshrss.list_categories()
        if categories:
            for cat in categories:
                print(f"  - {cat['name']}")
        else:
            print("  No se encontraron categorÃƒÂ­as")

        print("\n=== FEEDS ===")
        feeds = freshrss.list_feeds()
        if feeds:
            for feed in feeds:
                categories_str = ", ".join([c.get('label', '') for c in feed.get('categories', [])])
                print(f"  - {feed['title']}")
                print(f"    ID: {feed['id']}")
                if categories_str:
                    print(f"    CategorÃƒÂ­as: {categories_str}")
        else:
            print("  No se encontraron feeds")

        print("\nPara usar categorÃƒÂ­as/feeds especÃƒÂ­ficos, edita tu config.json")
        return

    # Verificar dependencias para traducciÃƒÂ³n
    if args.language:
        try:
            import langdetect
            from deep_translator import GoogleTranslator
            print(f"\nÃ¢Å“â€œ TraducciÃƒÂ³n automÃƒÂ¡tica habilitada (idioma destino: {args.language})")
        except ImportError as e:
            print(f"Ã¢Å“â€” Error: Falta instalar dependencias para traducciÃƒÂ³n")
            print("  Instala con: pip install langdetect deep-translator --break-system-packages")
            return

    # Verificar que edge-tts estÃƒÂ© instalado si se solicita
    if args.tts == 'edge':
        try:
            import edge_tts
        except ImportError:
            print("Ã¢Å“â€” edge-tts no estÃƒÂ¡ instalado. InstÃƒÂ¡lalo con:")
            print("  pip install edge-tts --break-system-packages")
            print("\nUsando gTTS como alternativa...")
            args.tts = 'gtts'

    # Si solo se quiere generar el XML, hacerlo y salir
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
            title = article.get('title', 'Sin tÃƒÂ­tulo')
            content = article.get('content', '')
            article_id = article.get('id')

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
                        # Marcar como leÃ­do si se solicitÃ³
                        if args.mark_as_read and article_id:
                            wallabag.mark_as_read(article_id)

    # Procesar FreshRSS
    if args.source in ['freshrss', 'both'] and 'freshrss' in config:
        print("\n=== FRESHRSS ===")
        fr_config = config['freshrss']
        freshrss = FreshRSSClient(
            fr_config['url'],
            fr_config['username'],
            fr_config['password']
        )

        # Obtener configuraciÃƒÂ³n de categorÃƒÂ­as y feeds
        categories = fr_config.get('categories', [])
        feeds = fr_config.get('feeds', [])
        default_limit = fr_config.get('limit', args.limit)
        default_original_language = fr_config.get('original-language')

        # Si no hay categorÃƒÂ­as ni feeds especÃƒÂ­ficos, obtener de reading-list
        if not categories and not feeds:
            print("Obteniendo artÃƒÂ­culos de reading-list (todos)...")
            articles = freshrss.get_articles(
                stream_id='reading-list',
                limit=default_limit,
                unread_only=fr_config.get('unread_only', True)
            )

            for article in articles:
                title = article.get('title', 'Sin tÃƒÂ­tulo')
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
                            # Marcar como leÃ­do si se solicitÃ³
                            if args.mark_as_read:
                                article_id = article.get('id')
                                if article_id:
                                    freshrss.mark_as_read(article_id)

        # Procesar categorÃƒÂ­as especÃƒÂ­ficas
        for category in categories:
            cat_name = category.get('name')
            cat_limit = category.get('limit', default_limit)
            cat_voice = category.get('voice', args.voice)
            cat_original_language = category.get('original-language', default_original_language)

            print(f"\nObteniendo artÃƒÂ­culos de categorÃƒÂ­a: {cat_name} (lÃƒÂ­mite: {cat_limit})...")
            stream_id = f"user/-/label/{cat_name}"
            articles = freshrss.get_articles(
                stream_id=stream_id,
                limit=cat_limit,
                unread_only=fr_config.get('unread_only', True)
            )

            print(f"Ã¢Å“â€œ {len(articles)} artÃƒÂ­culos de '{cat_name}'")

            # Actualizar voz si es especÃƒÂ­fica de la categorÃƒÂ­a
            if cat_voice != converter.voice:
                converter.voice = cat_voice

            for article in articles:
                title = article.get('title', 'Sin tÃƒÂ­tulo')
                content = ''
                if 'summary' in article and 'content' in article['summary']:
                    content = article['summary']['content']
                elif 'content' in article and 'content' in article['content']:
                    content = article['content']['content']

                if content:
                    text = converter.clean_text(content)
                    if text:
                        # Verificar si esta categorÃ­a incluye procesamiento de YouTube
                        cat_include_youtube = category.get('include_youtube', False)

                        if cat_include_youtube:
                            # Procesar con YouTube
                            filepath = converter.process_and_convert_with_youtube(
                                text,
                                content,  # HTML original
                                f"[{cat_name}] {title}",
                                original_language=cat_original_language,
                                lang=args.lang
                            )
                        else:
                            # Procesamiento normal
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
                            # Marcar como leÃ­do si se solicitÃ³
                            if args.mark_as_read:
                                article_id = article.get('id')
                                if article_id:
                                    freshrss.mark_as_read(article_id)

        # Procesar feeds especÃƒÂ­ficos
        for feed in feeds:
            feed_id = feed.get('id')
            feed_limit = feed.get('limit', default_limit)
            feed_name = feed.get('name', feed_id)
            feed_voice = feed.get('voice', args.voice)
            feed_original_language = feed.get('original-language', default_original_language)

            print(f"\nObteniendo artÃƒÂ­culos de feed: {feed_name} (lÃƒÂ­mite: {feed_limit})...")
            articles = freshrss.get_articles(
                stream_id=feed_id,
                limit=feed_limit,
                unread_only=fr_config.get('unread_only', True)
            )

            print(f"Ã¢Å“â€œ {len(articles)} artÃƒÂ­culos de '{feed_name}'")

            # Actualizar voz si es especÃƒÂ­fica del feed
            if feed_voice != converter.voice:
                converter.voice = feed_voice

            for article in articles:
                title = article.get('title', 'Sin tÃƒÂ­tulo')
                content = ''
                if 'summary' in article and 'content' in article['summary']:
                    content = article['summary']['content']
                elif 'content' in article and 'content' in article['content']:
                    content = article['content']['content']

                if content:
                    text = converter.clean_text(content)
                    if text:
                        # Verificar si este feed incluye procesamiento de YouTube
                        feed_include_youtube = feed.get('include_youtube', False)

                        if feed_include_youtube:
                            # Procesar con YouTube
                            filepath = converter.process_and_convert_with_youtube(
                                text,
                                content,  # HTML original
                                f"[{feed_name}] {title}",
                                original_language=feed_original_language,
                                lang=args.lang
                            )
                        else:
                            # Procesamiento normal
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
                            # Marcar como leÃ­do si se solicitÃ³
                            if args.mark_as_read:
                                article_id = article.get('id')
                                if article_id:
                                    freshrss.mark_as_read(article_id)

    print(f"\nÃ¢Å“â€œ Proceso completado. {articles_processed} artÃƒÂ­culos convertidos a MP3")
    print(f"Ã¢Å“â€œ Motor TTS usado: {args.tts}")
    if args.tts == 'edge':
        print(f"Ã¢Å“â€œ Voz usada: {args.voice}")
    if args.language:
        print(f"Ã¢Å“â€œ TraducciÃƒÂ³n automÃƒÂ¡tica: activada (destino: {args.language})")
    print(f"Ã¢Å“â€œ Omitir existentes: {'SÃƒÂ­' if args.skip_existing else 'No'}")
    if args.mark_as_read:
        print(f"âœ“ Marcar como leÃ­do: SÃ­")
    print(f"Ã¢Å“â€œ Archivos guardados en: {args.output}")

    # Generar feed RSS si se solicitÃƒÂ³
    if args.generate_feed and feed_generator and feed_generator.episodes:
        feed_generator.generate_rss()


if __name__ == "__main__":
    main()
