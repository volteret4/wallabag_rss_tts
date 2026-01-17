#!/usr/bin/env python3
"""
Servidor HTTP simple para servir el podcast
Sirve los archivos MP3 y el feed RSS en la red de Tailscale
"""

import http.server
import socketserver
import os
import argparse
import json


class PodcastHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Handler HTTP personalizado para servir el podcast"""

    def end_headers(self):
        # Añadir headers CORS para permitir acceso desde cualquier origen
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def do_GET(self):
        # Log de las peticiones
        print(f"[{self.date_time_string()}] GET {self.path}")
        super().do_GET()


def main():
    parser = argparse.ArgumentParser(
        description='Servidor HTTP para el podcast TTS',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  # Servidor en puerto 8000 (predeterminado)
  python3 podcast_server.py

  # Servidor en puerto específico
  python3 podcast_server.py --port 9000

  # Directorio de audio personalizado
  python3 podcast_server.py --dir mis_audios

  # Bind a dirección específica
  python3 podcast_server.py --host 0.0.0.0
        """
    )

    parser.add_argument('--port', type=int, default=8000,
                       help='Puerto del servidor (default: 8000)')
    parser.add_argument('--host', default='0.0.0.0',
                       help='Dirección IP a la que bind (default: 0.0.0.0 = todas)')
    parser.add_argument('--dir', default='audio_articles',
                       help='Directorio de archivos de audio (default: audio_articles)')

    args = parser.parse_args()

    # Verificar que el directorio existe
    if not os.path.exists(args.dir):
        print(f"✗ Error: El directorio '{args.dir}' no existe")
        print(f"   Créalo primero o ejecuta el script de conversión")
        return

    # Cambiar al directorio de audio
    os.chdir(args.dir)

    # Crear servidor
    handler = PodcastHTTPRequestHandler

    try:
        with socketserver.TCPServer((args.host, args.port), handler) as httpd:
            print(f"")
            print(f"🎙️  Servidor de Podcast TTS iniciado")
            print(f"=" * 60)
            print(f"Directorio: {os.getcwd()}")
            print(f"Escuchando en: {args.host}:{args.port}")
            print(f"")
            print(f"📱 URLs de acceso:")
            print(f"   Local:     http://localhost:{args.port}/")
            print(f"   Red local: http://<tu-ip-local>:{args.port}/")

            # Intentar obtener la IP de Tailscale
            try:
                import subprocess
                result = subprocess.run(['tailscale', 'ip', '-4'],
                                      capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    tailscale_ip = result.stdout.strip()
                    print(f"   Tailscale: http://{tailscale_ip}:{args.port}/")
                    print(f"")
                    print(f"📡 Feed RSS del podcast:")
                    print(f"   http://{tailscale_ip}:{args.port}/podcast.xml")
            except Exception:
                pass

            print(f"")
            print(f"Para detener el servidor presiona Ctrl+C")
            print(f"=" * 60)
            print(f"")

            httpd.serve_forever()

    except KeyboardInterrupt:
        print("\n\n✓ Servidor detenido")
    except OSError as e:
        if e.errno == 98:
            print(f"\n✗ Error: El puerto {args.port} ya está en uso")
            print(f"   Prueba con otro puerto: --port 9000")
        else:
            print(f"\n✗ Error: {e}")


if __name__ == "__main__":
    main()
