#!/usr/bin/env python3
"""
Servidor web simple para la interfaz de selección de artículos
Recibe las selecciones y lanza automáticamente la conversión a MP3
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import os
import subprocess
import threading
import time
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Configuración - ajustar según tu setup
WORK_DIR = os.path.expanduser("~/podcast-tts")  # Directorio de trabajo
SELECTION_FILE = os.path.join(WORK_DIR, "selection.json")
STATUS_FILE = os.path.join(WORK_DIR, "conversion_status.json")
LOG_FILE = os.path.join(WORK_DIR, "conversion_log.txt")
ARTICLES_DATA_FILE = os.path.join(WORK_DIR, "articles_data.json")

# Crear directorio de trabajo si no existe
os.makedirs(WORK_DIR, exist_ok=True)

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


def run_conversion():
    """Ejecuta el script de conversión en un hilo separado"""
    global conversion_status

    try:
        update_status(progress=0, current_article="Iniciando conversión...")

        # Cambiar al directorio de trabajo
        os.chdir(WORK_DIR)

        # Lanzar el script de procesamiento
        process = subprocess.Popen(
            ['python3', 'process_selection.py', '--selection', SELECTION_FILE, '--generate-feed'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        # Leer la salida en tiempo real
        with open(LOG_FILE, 'w') as log:
            for line in process.stdout:
                log.write(line)
                log.flush()

                # Parsear el progreso
                if "Procesando" in line:
                    try:
                        parts = line.split(":")
                        if len(parts) >= 2:
                            progress_part = parts[0].strip()
                            title = ":".join(parts[1:]).strip()

                            if "/" in progress_part:
                                nums = progress_part.split("/")[-1].split()
                                if len(nums) >= 1:
                                    current = int(nums[0].split("/")[0].split()[-1])
                                    total = int(nums[0].split("/")[1])
                                    update_status(progress=current, total=total, current_article=title)
                    except Exception as e:
                        print(f"Error parseando progreso: {e}")

        # Esperar a que termine
        return_code = process.wait()

        if return_code == 0:
            update_status(finished=True, current_article="¡Conversión completada!")
        else:
            stderr = process.stderr.read()
            update_status(error=f"Error en conversión: {stderr}", finished=True)

    except Exception as e:
        update_status(error=f"Error ejecutando conversión: {str(e)}", finished=True)


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
        # Verificar que no haya una conversión en curso
        if conversion_status["running"]:
            return jsonify({
                "success": False,
                "message": "Ya hay una conversión en curso. Espera a que termine."
            }), 400

        # Obtener datos
        selection = request.json

        # Contar artículos seleccionados
        total_articles = len(selection.get('wallabag', []))
        for category in selection.get('freshrss', {}).get('categories', {}).values():
            for feed_articles in category.values():
                total_articles += len(feed_articles)

        if total_articles == 0:
            return jsonify({
                "success": False,
                "message": "No hay artículos seleccionados"
            }), 400

        # Guardar selección
        with open(SELECTION_FILE, 'w', encoding='utf-8') as f:
            json.dump(selection, f, ensure_ascii=False, indent=2)

        # Inicializar estado
        conversion_status = {
            "running": True,
            "progress": 0,
            "total": total_articles,
            "current_article": "Iniciando...",
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "errors": []
        }
        update_status()

        # Lanzar conversión en hilo separado
        thread = threading.Thread(target=run_conversion)
        thread.daemon = True
        thread.start()

        return jsonify({
            "success": True,
            "message": f"Conversión iniciada para {total_articles} artículos",
            "path": os.path.abspath(SELECTION_FILE),
            "total_articles": total_articles
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error: {str(e)}"
        }), 500


@app.route('/api/conversion-status', methods=['GET'])
def get_conversion_status():
    """Obtener el estado actual de la conversión"""
    return jsonify(conversion_status)


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
    return jsonify({"status": "ok", "working_dir": WORK_DIR})


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
