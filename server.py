#!/usr/bin/env python3
"""
Servidor web simple para la interfaz de selección de artículos
Recibe las selecciones y lanza automáticamente la conversión a MP3
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import os
import queue as _queue_lib
import re
import subprocess
import threading
import time
from datetime import datetime
import sys

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mGKHFJ]|\r')

def _clean(line):
    return _ANSI_RE.sub('', line).strip()

app = Flask(__name__)
CORS(app)

# Configuración - ajustar según tu setup
WORK_DIR = os.path.expanduser("~/contenedores/podcast-tts")  # Directorio de trabajo
SELECTION_FILE = os.path.join(WORK_DIR, "selection.json")
STATUS_FILE = os.path.join(WORK_DIR, "conversion_status.json")
LOG_FILE = os.path.join(WORK_DIR, "conversion_log.txt")
ARTICLES_DATA_FILE = os.path.join(WORK_DIR, "articles_data.json")
CONFIG_FILE = os.path.join(WORK_DIR, "config.json")

# Crear directorio de trabajo si no existe
os.makedirs(WORK_DIR, exist_ok=True)

# Cola de trabajos de conversión (procesada por _conversion_worker)
_job_queue = _queue_lib.Queue()

# Estado global del refresh de artículos
refresh_status = {
    "running": False,
    "finished_at": None,
    "error": None,
    "message": "Sin actualizar"
}

# Estado global del proceso
conversion_status = {
    "running": False,
    "progress": 0,
    "total": 0,
    "current_article": "",
    "started_at": None,
    "finished_at": None,
    "errors": []
}


def update_status(progress=None, total=None, current_article=None, error=None, finished=False):
    """Actualiza el estado de la conversión"""
    global conversion_status

    if progress is not None:
        conversion_status["progress"] = progress
    if total is not None:
        conversion_status["total"] = total
    if current_article is not None:
        conversion_status["current_article"] = current_article
    if error is not None:
        conversion_status["errors"].append(error)
    if finished:
        conversion_status["running"] = False
        conversion_status["finished_at"] = datetime.now().isoformat()

    # Guardar en archivo
    with open(STATUS_FILE, 'w') as f:
        json.dump(conversion_status, f, indent=2)


def run_conversion(selection_file=None):
    """Ejecuta el script de conversión."""
    global conversion_status

    if selection_file is None:
        selection_file = SELECTION_FILE

    try:
        print("🔄 Iniciando conversión...")
        update_status(progress=0, current_article="Iniciando conversión...")

        print(f"📁 Cambiando a directorio: {WORK_DIR}")
        os.chdir(WORK_DIR)

        if not os.path.exists('process_selection.py'):
            error_msg = f"❌ No se encuentra process_selection.py en {WORK_DIR}"
            print(error_msg)
            update_status(error=error_msg, finished=True)
            return

        if not os.path.exists(selection_file):
            error_msg = f"❌ No se encuentra {selection_file}"
            print(error_msg)
            update_status(error=error_msg, finished=True)
            return

        cmd = [sys.executable, 'process_selection.py', '--selection', selection_file, '--generate-feed']
        print(f"🚀 Ejecutando: {' '.join(cmd)}")

        # Lanzar el script de procesamiento
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Redirigir stderr a stdout
            text=True,
            bufsize=1
        )

        print(f"✅ Proceso iniciado con PID: {process.pid}")

        # Leer la salida en tiempo real
        with open(LOG_FILE, 'w') as log:
            log.write(f"=== Conversión iniciada a las {datetime.now()} ===\n")
            log.write(f"Comando: {' '.join(cmd)}\n")
            log.write(f"PID: {process.pid}\n")
            log.write("=" * 60 + "\n\n")
            log.flush()

            for line in process.stdout:
                clean = _clean(line)
                if not clean:
                    continue
                log.write(clean + '\n')
                log.flush()
                print(f"[PROCESO] {clean}")

                m = re.search(r'Procesando\s+(\d+)/(\d+):\s*(.+)', clean)
                if m:
                    current_n, total_n, title = int(m.group(1)), int(m.group(2)), m.group(3)
                    update_status(progress=current_n, total=total_n, current_article=title)

        # Esperar a que termine
        return_code = process.wait()
        print(f"🏁 Proceso terminado con código: {return_code}")

        if return_code == 0:
            print("✅ Conversión completada exitosamente")
            update_status(finished=True, current_article="¡Conversión completada!")
        else:
            error_msg = f"❌ Proceso terminó con código de error: {return_code}"
            print(error_msg)
            update_status(error=error_msg, finished=True)

    except Exception as e:
        error_msg = f"💥 Error ejecutando conversión: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        update_status(error=error_msg, finished=True)
    finally:
        # Clean up timestamped selection files created by the queue
        if selection_file and selection_file != SELECTION_FILE:
            try:
                os.unlink(selection_file)
            except OSError:
                pass


def _conversion_worker():
    """Worker que procesa los trabajos de conversión uno a uno."""
    while True:
        job = _job_queue.get()
        try:
            kind = job['kind']
            if kind == 'selection':
                run_conversion(job['selection_file'])
            elif kind == 'url':
                _run_url_conversion(**job['kwargs'])
        except Exception as e:
            update_status(error=f"Worker error: {e}", finished=True)
        finally:
            _job_queue.task_done()


def run_fetch_articles():
    """Ejecuta fetch_articles.py para regenerar el JSON de artículos"""
    global refresh_status

    try:
        # Buscar fetch_articles.py en múltiples ubicaciones
        fetch_script = None
        server_dir = os.path.dirname(os.path.abspath(__file__))
        for candidate in [
            os.path.join(WORK_DIR, 'fetch_articles.py'),
            os.path.join(server_dir, 'web', 'fetch_articles.py'),
            os.path.join(server_dir, 'fetch_articles.py'),
        ]:
            if os.path.exists(candidate):
                fetch_script = candidate
                break

        if not fetch_script:
            refresh_status.update({"running": False, "error": "No se encontró fetch_articles.py", "message": "Error: script no encontrado"})
            return

        # Buscar config.json
        config_file = None
        for candidate in [
            os.path.join(WORK_DIR, 'config', 'config.json'),
            os.path.join(WORK_DIR, 'config.json'),
            os.path.join(server_dir, 'docker', 'config.json'),
        ]:
            if os.path.exists(candidate):
                config_file = candidate
                break

        cmd = [sys.executable, fetch_script, '--output', ARTICLES_DATA_FILE]
        if config_file:
            cmd += ['--config', config_file]

        refresh_status["message"] = "Conectando con Wallabag y FreshRSS..."
        process = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

        if process.returncode == 0:
            refresh_status.update({
                "running": False,
                "finished_at": datetime.now().isoformat(),
                "error": None,
                "message": "Artículos actualizados correctamente"
            })
        else:
            err = process.stderr or process.stdout or "Error desconocido"
            refresh_status.update({"running": False, "error": err[:500], "message": "Error al actualizar"})

    except subprocess.TimeoutExpired:
        refresh_status.update({"running": False, "error": "Timeout (>3 min)", "message": "Error: timeout"})
    except Exception as e:
        refresh_status.update({"running": False, "error": str(e), "message": f"Error: {str(e)}"})


@app.route('/api/refresh-articles', methods=['POST'])
def refresh_articles():
    """Lanza fetch_articles.py en background para actualizar el JSON"""
    global refresh_status

    if refresh_status.get("running"):
        return jsonify({"success": False, "message": "Ya hay una actualización en curso"}), 400

    refresh_status = {"running": True, "finished_at": None, "error": None, "message": "Iniciando..."}
    thread = threading.Thread(target=run_fetch_articles, name="FetchThread", daemon=True)
    thread.start()
    return jsonify({"success": True, "message": "Actualización iniciada"})


@app.route('/api/refresh-status', methods=['GET'])
def get_refresh_status():
    """Estado de la actualización de artículos"""
    return jsonify(refresh_status)


@app.route('/api/articles_data.json')
def articles_data():
    """Servir el JSON de artículos"""
    if os.path.exists(ARTICLES_DATA_FILE):
        return send_from_directory(WORK_DIR, 'articles_data.json')
    else:
        return jsonify({"error": "articles_data.json no encontrado"}), 404


@app.route('/api/save-selection', methods=['POST'])
def save_selection():
    """Guardar la selección y lanzar conversión"""
    global conversion_status

    try:
        print("\n" + "="*60)
        print("📥 Nueva petición de conversión recibida")

        selection = request.json
        print(f"📊 Datos recibidos: {len(str(selection))} caracteres")

        total_articles = len(selection.get('wallabag', []))
        for category in selection.get('freshrss', {}).get('categories', {}).values():
            for feed_articles in category.values():
                total_articles += len(feed_articles)

        print(f"📋 Total de artículos seleccionados: {total_articles}")

        if total_articles == 0:
            return jsonify({"success": False, "message": "No hay artículos seleccionados"}), 400

        # Save to a unique file so concurrent queue jobs don't overwrite each other
        sel_file = f"{SELECTION_FILE}.{int(time.time() * 1000)}"
        with open(sel_file, 'w', encoding='utf-8') as f:
            json.dump(selection, f, ensure_ascii=False, indent=2)
        print(f"💾 Selección guardada en: {sel_file}")

        _job_queue.put({'kind': 'selection', 'selection_file': sel_file})
        queue_pos = _job_queue.qsize()
        print(f"📥 Trabajo añadido a la cola (tamaño={queue_pos})")
        print("=" * 60 + "\n")

        return jsonify({
            "success": True,
            "message": f"{total_articles} artículos añadidos a la cola (posición {queue_pos})",
            "total_articles": total_articles,
            "queue_position": queue_pos,
        })

    except Exception as e:
        error_msg = f"💥 Error en save_selection: {str(e)}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": f"Error: {str(e)}"
        }), 500


@app.route('/api/conversion-status', methods=['GET'])
def get_conversion_status():
    """Obtener el estado actual de la conversión"""
    return jsonify({**conversion_status, 'queue_size': _job_queue.qsize()})


@app.route('/api/conversion-log', methods=['GET'])
def get_conversion_log():
    """Obtener el log de conversión"""
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r') as f:
                return jsonify({
                    "success": True,
                    "log": f.read()
                })
        else:
            return jsonify({
                "success": True,
                "log": "No hay log disponible"
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "working_dir": WORK_DIR,
        "selection_file_exists": os.path.exists(SELECTION_FILE),
        "conversion_running": conversion_status["running"],
        "timestamp": datetime.now().isoformat()
    })


@app.route('/api/debug', methods=['GET'])
def debug_info():
    """Endpoint de debug para ver el estado del sistema"""
    import threading

    debug_data = {
        "working_dir": WORK_DIR,
        "files_exist": {
            "process_selection.py": os.path.exists(os.path.join(WORK_DIR, 'process_selection.py')),
            "articles_to_mp3.py": os.path.exists(os.path.join(WORK_DIR, 'articles_to_mp3.py')),
            "config.json": os.path.exists(os.path.join(WORK_DIR, 'config.json')),
            "selection.json": os.path.exists(SELECTION_FILE),
            "articles_data.json": os.path.exists(ARTICLES_DATA_FILE)
        },
        "conversion_status": conversion_status,
        "active_threads": [t.name for t in threading.enumerate()],
        "log_exists": os.path.exists(LOG_FILE),
        "log_size": os.path.getsize(LOG_FILE) if os.path.exists(LOG_FILE) else 0
    }

    return jsonify(debug_data)


@app.route('/api/convert-url', methods=['POST'])
def api_convert_url():
    """Convierte una URL de artículo a MP3 y actualiza el feed."""
    global conversion_status

    data = request.json or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({"success": False, "error": "URL requerida"}), 400

    voice = data.get('voice', 'es-ES-AlvaroNeural')
    language = data.get('language', 'auto')
    include_youtube = bool(data.get('include_youtube', False))
    title = data.get('title', '')

    _job_queue.put({'kind': 'url', 'kwargs': {
        'url': url, 'voice': voice, 'language': language,
        'include_youtube': include_youtube, 'title': title,
    }})
    queue_pos = _job_queue.qsize()

    return jsonify({
        "success": True,
        "message": f"Añadido a la cola (posición {queue_pos})" if queue_pos > 1 else "Conversión iniciada",
        "queue_position": queue_pos,
    })


def _run_url_conversion(url, voice, language, include_youtube, title):
    server_dir = os.path.dirname(os.path.abspath(__file__))
    convert_script = None
    for candidate in [
        os.path.join(WORK_DIR, 'convert_url.py'),
        os.path.join(server_dir, 'convert_url.py'),
    ]:
        if os.path.exists(candidate):
            convert_script = candidate
            break

    if not convert_script:
        update_status(error="No se encontró convert_url.py", finished=True)
        return

    os.chdir(WORK_DIR)

    cmd = [
        sys.executable, convert_script,
        '--url', url,
        '--voice', voice,
        '--language', language,
    ]
    if include_youtube:
        cmd.append('--include-youtube')
    if title:
        cmd += ['--title', title]

    try:
        with open(LOG_FILE, 'a') as log:
            log.write(f"\n=== convert-url {datetime.now()} ===\nURL: {url}\n\n")
            log.flush()

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            for line in process.stdout:
                clean = _clean(line)
                if not clean:
                    continue
                log.write(clean + '\n')
                log.flush()
                print(f"[URL-CONV] {clean}")

                m = re.search(r'Procesando\s+(\d+)/(\d+):\s*(.+)', clean)
                if m:
                    update_status(
                        progress=int(m.group(1)),
                        total=int(m.group(2)),
                        current_article=m.group(3),
                    )

        rc = process.wait()
        if rc == 0:
            update_status(progress=1, total=1, finished=True, current_article="¡Conversión completada!")
        else:
            update_status(error=f"Proceso terminó con código {rc}", finished=True)
    except Exception as e:
        update_status(error=str(e), finished=True)


@app.route('/api/config', methods=['GET'])
def get_config():
    try:
        if not os.path.exists(CONFIG_FILE):
            return jsonify({"success": False, "error": "config.json no encontrado"}), 404
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return jsonify({"success": True, "config": config})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/config', methods=['POST'])
def save_config():
    try:
        config = request.json
        if not config:
            return jsonify({"success": False, "error": "No se recibieron datos"}), 400
        # Backup antes de guardar
        if os.path.exists(CONFIG_FILE):
            import shutil
            shutil.copy2(CONFIG_FILE, CONFIG_FILE + '.bak')
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        return jsonify({"success": True, "message": "Configuración guardada correctamente"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# Start the single conversion worker thread (processes jobs sequentially)
_worker = threading.Thread(target=_conversion_worker, daemon=True, name='ConversionWorker')
_worker.start()


if __name__ == '__main__':
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   📚 Servidor de Conversión de Artículos a MP3               ║
║                                                               ║
║   📁 Directorio de trabajo: {WORK_DIR:<30} ║
║                                                               ║
║   🌐 Servidor corriendo en:                                   ║
║      http://0.0.0.0:5000                                      ║
║                                                               ║
║   📝 Endpoints API:                                           ║
║      POST   /api/save-selection      - Guardar y convertir   ║
║      GET    /api/conversion-status   - Ver progreso          ║
║      GET    /api/conversion-log      - Ver log detallado     ║
║      GET    /api/articles_data.json  - Datos de artículos    ║
║      GET    /health                  - Health check          ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """)

    # Correr en 0.0.0.0:5000 para ser accesible desde fuera del contenedor
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
