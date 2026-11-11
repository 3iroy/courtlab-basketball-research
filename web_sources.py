"""Bounded retrieval of public web passages for the research evidence registry."""
import asyncio
import hashlib
import os
import re
from datetime import date, datetime, timezone
from urllib.parse import quote, urlsplit

import httpx

SEARCH_URL = 'https://api.tavily.com/search'
MAX_WEB_SEARCHES = 3


def search_available():
    return bool(os.getenv('TAVILY_API_KEY', '').strip())


def public_source_url(value):
    if not isinstance(value, str) or len(value) > 2048 or re.search(r'[\s\\]', value):
        return None
    try:
        url = urlsplit(value)
    except ValueError:
        return None
    if url.scheme != 'https' or not re.fullmatch(
        r'(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}', url.netloc, re.I
    ):
        return None
    return quote(value, safe=':/?#@!$&*+,;=%')


def passages(results):
    retrieved = datetime.now(timezone.utc).date().isoformat()
    found = []
    seen = set()
    for result in results[:3]:
        if not isinstance(result, dict):
            continue
        url = public_source_url(result.get('url'))
        title = result.get('title')
        excerpt = result.get('content')
        if not url or url in seen or not isinstance(title, str) or not isinstance(excerpt, str):
            continue
        title = ' '.join(title.replace('[', '').replace(']', '').split())[:200]
        excerpt = excerpt.strip()[:1300]
        if not title or not excerpt:
            continue
        seen.add(url)
        published = result.get('published_date')
        try:
            published = date.fromisoformat(str(published)[:10]).isoformat()
        except ValueError:
            published = None
        locator = 'Web excerpt · ' + urlsplit(url).hostname
        if published:
            locator += f' · published {published}'
        locator += f' · retrieved {retrieved}'
        digest = hashlib.sha256((url + '\n' + excerpt).encode()).hexdigest()[:24]
        found.append({
            'source_id': 'web-' + digest,
            'title': title,
            'url': url,
            'evidence_url': url,
            'locator': locator,
            'text': excerpt,
            'kind': 'web_article',
        })
    return found


async def search(query):
    key = os.getenv('TAVILY_API_KEY', '').strip()
    if not key:
        return {'error': 'Web search is not configured.'}
    if not query:
        return {'error': 'Provide a short public basketball search query.'}
    try:
        async with asyncio.timeout(12), httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                SEARCH_URL,
                headers={'Authorization': f'Bearer {key}'},
                json={
                    'query': query,
                    'search_depth': 'basic',
                    'chunks_per_source': 2,
                    'max_results': 3,
                    'include_answer': False,
                    'include_published_date': True,
                },
            )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get('results'), list):
            return {'error': 'Web search returned an invalid response.'}
        return {'passages': passages(data['results'])}
    except (TimeoutError, httpx.HTTPError, ValueError):
        return {'error': 'Web search is temporarily unavailable.'}
