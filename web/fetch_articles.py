#!/usr/bin/env python3
"""
Script para obtener todos los feeds de FreshRSS y artículos de Wallabag
y guardarlos en un JSON para la interfaz web de selección
Versión mejorada: organiza artículos por Categoría > Feed > Artículos
"""

import os
import json
import requests
import argparse
from datetime import datetime
from collections import defaultdict


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

    def get_all_articles(self, archive=0, limit=100):
        """Obtiene todos los artículos de Wallabag (paginado)"""
        if not self.token:
            if not self.authenticate():
                return []

        headers = {'Authorization': f'Bearer {self.token}'}

        all_articles = []
        page = 1

        while True:
            params = {
                'archive': archive,
                'perPage': limit,
                'page': page,
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
                data = response.json()
                articles = data['_embedded']['items']

                if not articles:
                    break

                all_articles.extend(articles)
                print(f"  Página {page}: {len(articles)} artículos")
                page += 1

                # Si hay menos artículos que el límite, es la última página
                if len(articles) < limit:
                    break

            except Exception as e:
                print(f"✗ Error al obtener artículos de Wallabag: {e}")
                break

        print(f"✓ Total de artículos en Wallabag: {len(all_articles)}")
        return all_articles


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
                feed_categories = []

                for cat in sub.get('categories', []):
                    if 'label' in cat:
                        feed_categories.append(cat['label'])

                feeds.append({
                    'id': feed_id,
                    'title': sub.get('title', ''),
                    'categories': feed_categories,
                    'url': sub.get('htmlUrl', '')
                })

            return feeds
        except Exception as e:
            print(f"✗ Error al listar feeds: {e}")
            return []

    def get_articles(self, stream_id=None, limit=100, unread_only=False):
        """Obtiene artículos de FreshRSS"""
        if not self.auth_token:
            if not self.authenticate():
                return []

        # Construir URL del stream
        if stream_id:
            if stream_id == 'reading-list':
                stream_path = 'reading-list'
            elif stream_id.startswith('user/-/label/'):
                stream_path = f"contents/{stream_id}"
            elif stream_id.startswith('feed/'):
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


def fetch_all_data(config_file='config.json', output_file='articles_data.json'):
    """Obtiene todos los datos de FreshRSS y Wallabag y los guarda en JSON"""

    # Cargar configuración
    if not os.path.exists(config_file):
        print(f"✗ No se encuentra el archivo de configuración: {config_file}")
        return False

    with open(config_file, 'r') as f:
        config = json.load(f)

    result = {
        'generated_at': datetime.now().isoformat(),
        'wallabag': {
            'enabled': 'wallabag' in config,
            'articles': []
        },
        'freshrss': {
            'enabled': 'freshrss' in config,
            'categories': []
        }
    }

    # Obtener datos de Wallabag
    if 'wallabag' in config:
        print("\n=== WALLABAG ===")
        wb_config = config['wallabag']
        wallabag = WallabagClient(
            wb_config['url'],
            wb_config['client_id'],
            wb_config['client_secret'],
            wb_config['username'],
            wb_config['password']
        )

        articles = wallabag.get_all_articles()

        for article in articles:
            result['wallabag']['articles'].append({
                'id': article.get('id'),
                'title': article.get('title', 'Sin título'),
                'url': article.get('url', ''),
                'created_at': article.get('created_at', ''),
                'word_count': len(article.get('content', '').split()),
                'char_count': len(article.get('content', '')),
                'is_archived': article.get('is_archived', False),
                'is_starred': article.get('is_starred', False),
                'tags': [tag['label'] for tag in article.get('tags', [])]
            })

    # Obtener datos de FreshRSS
    if 'freshrss' in config:
        print("\n=== FRESHRSS ===")
        fr_config = config['freshrss']
        freshrss = FreshRSSClient(
            fr_config['url'],
            fr_config['username'],
            fr_config['password']
        )

        # Obtener categorías
        print("\nObteniendo categorías...")
        categories = freshrss.list_categories()
        print(f"✓ {len(categories)} categorías encontradas")

        # Obtener feeds
        print("\nObteniendo feeds...")
        all_feeds = freshrss.list_feeds()
        print(f"✓ {len(all_feeds)} feeds encontrados")

        # Organizar feeds por categoría
        feeds_by_category = defaultdict(list)
        for feed in all_feeds:
            for cat in feed['categories']:
                feeds_by_category[cat].append(feed)

        # Para cada categoría, obtener artículos organizados por feed
        print("\nObteniendo artículos organizados por categoría y feed...")
        for category in categories:
            cat_name = category['name']
            print(f"\n📁 Categoría: {cat_name}")

            category_data = {
                'id': category['id'],
                'name': cat_name,
                'feeds': []
            }

            # Obtener feeds de esta categoría
            cat_feeds = feeds_by_category.get(cat_name, [])

            for feed in cat_feeds:
                print(f"  📰 Feed: {feed['title']}")

                # Obtener artículos de este feed
                articles = freshrss.get_articles(
                    stream_id=feed['id'],
                    limit=100,
                    unread_only=False
                )

                articles_data = []
                for article in articles:
                    content = ''
                    if 'summary' in article and 'content' in article['summary']:
                        content = article['summary']['content']
                    elif 'content' in article and 'content' in article['content']:
                        content = article['content']['content']

                    articles_data.append({
                        'id': article.get('id', ''),
                        'title': article.get('title', 'Sin título'),
                        'published': article.get('published', 0),
                        'updated': article.get('updated', 0),
                        'author': article.get('author', ''),
                        'word_count': len(content.split()),
                        'char_count': len(content),
                        'alternate': article.get('alternate', [{}])[0].get('href', '') if article.get('alternate') else ''
                    })

                feed_data = {
                    'id': feed['id'],
                    'title': feed['title'],
                    'url': feed['url'],
                    'article_count': len(articles_data),
                    'articles': articles_data
                }

                category_data['feeds'].append(feed_data)
                print(f"    ✓ {len(articles_data)} artículos")

            result['freshrss']['categories'].append(category_data)

    # Guardar resultado
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Datos guardados en: {output_file}")

    # Resumen
    print("\n=== RESUMEN ===")
    if result['wallabag']['enabled']:
        print(f"Wallabag: {len(result['wallabag']['articles'])} artículos")
    if result['freshrss']['enabled']:
        print(f"FreshRSS:")
        total_feeds = sum(len(cat['feeds']) for cat in result['freshrss']['categories'])
        total_articles = sum(
            feed['article_count']
            for cat in result['freshrss']['categories']
            for feed in cat['feeds']
        )
        print(f"  - {len(result['freshrss']['categories'])} categorías")
        print(f"  - {total_feeds} feeds")
        print(f"  - {total_articles} artículos totales")

    return True


def main():
    parser = argparse.ArgumentParser(
        description='Obtiene todos los artículos disponibles de FreshRSS y Wallabag'
    )
    parser.add_argument('--config', default='config.json',
                       help='Archivo de configuración JSON')
    parser.add_argument('--output', default='articles_data.json',
                       help='Archivo JSON de salida con todos los artículos')

    args = parser.parse_args()

    fetch_all_data(args.config, args.output)


if __name__ == "__main__":
    main()
