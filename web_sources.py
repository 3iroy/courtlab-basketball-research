"""Bounded retrieval of public web passages for the research evidence registry."""
import asyncio
import hashlib
import os
import re
from datetime import date, datetime, timezone
from urllib.parse import quote, urlsplit

import httpx
from bs4 import BeautifulSoup

SEARCH_URL = 'https://api.tavily.com/search'
DBB_TEAM_URL = 'https://www.basketball-bund.de/team/a-herren/'
DBB_QUALIFIER_TITLE = re.compile(r'^world cup qualifier herren\b', re.I)
DBB_GAME_SCORE = re.compile(r'\b\d{2,3}\s*[:–-]\s*\d{2,3}\b')
DBB_RESULT = re.compile(r'\b(?:siegte|setzte|gewann|unterlag|verlor|endete|schlug|bezwingen)\b', re.I)
DBB_ACTION = re.compile(
    r'pick[\s-]*(?:and|n)?[\s-]*roll|zonenverteidigung|fast[\s-]*break|'
    r'umschalt\w*|offensiv\w* brett|alley[\s-]+oop|switch\w*|hand[\s-]*off',
    re.I,
)
MAX_WEB_SEARCHES = 3
DOMAIN = re.compile(r'(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}', re.I)


def search_available():
    return bool(os.getenv('TAVILY_API_KEY', '').strip())


def public_source_url(value):
    if not isinstance(value, str) or len(value) > 2048 or re.search(r'[\s\\]', value):
        return None
    try:
        url = urlsplit(value)
    except ValueError:
        return None
    if url.scheme != 'https' or not DOMAIN.fullmatch(url.netloc):
        return None
    return quote(value, safe=':/?#@!$&*+,;=%')


def expand_excerpt(excerpt, raw_content, query):
    """Add relevant paragraphs from the publisher page to the search snippets."""
    if not isinstance(raw_content, str):
        return excerpt
    stop_words = {'about', 'from', 'game', 'film', 'study', 'what', 'when', 'where', 'with'}
    terms = set(re.findall(r'[a-z0-9]{4,}', query.lower())) - stop_words
    candidates = (' '.join(line.split()) for line in raw_content[:20000].splitlines())
    candidates = [line for line in candidates if 100 <= len(line) <= 950 and line not in excerpt]
    ranked = sorted(dict.fromkeys(candidates),
                    key=lambda line: sum(term in line.lower() for term in terms), reverse=True)
    for paragraph in ranked[:3]:
        if len(excerpt) + len(paragraph) + 11 <= 2800 and any(term in paragraph.lower() for term in terms):
            excerpt += '\n\n[...]\n\n' + paragraph
    return excerpt


def passages(results, query, domain):
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
        hostname = urlsplit(url).hostname
        if domain and hostname != domain and not hostname.endswith('.' + domain):
            continue
        title = ' '.join(title.replace('[', '').replace(']', '').split())[:200]
        excerpt = excerpt.strip()[:1300]
        if not title or not excerpt:
            continue
        if domain:
            excerpt = expand_excerpt(excerpt, result.get('raw_content'), query)
        seen.add(url)
        published = result.get('published_date')
        try:
            published = date.fromisoformat(str(published)[:10]).isoformat()
        except ValueError:
            published = None
        locator = 'Web excerpt · ' + hostname
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


async def search(query, domain=""):
    key = os.getenv('TAVILY_API_KEY', '').strip()
    if not key:
        return {'error': 'Web search is not configured.'}
    if not query:
        return {'error': 'Provide a short public basketball search query.'}
    domain = domain.strip().lower().removeprefix('www.')
    if domain and not DOMAIN.fullmatch(domain):
        return {'error': 'Use a publisher domain such as nba.com.'}
    payload = {
        'query': query,
        'search_depth': 'basic',
        'chunks_per_source': 2,
        'max_results': 3,
        'include_answer': False,
        'include_published_date': True,
    }
    if domain:
        payload.update(include_domains=[domain], include_raw_content='text')
    try:
        async with asyncio.timeout(12), httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                SEARCH_URL,
                headers={'Authorization': f'Bearer {key}'},
                json=payload,
            )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get('results'), list):
            return {'error': 'Web search returned an invalid response.'}
        return {'passages': passages(data['results'], query, domain)}
    except (TimeoutError, httpx.HTTPError, ValueError):
        return {'error': 'Web search is temporarily unavailable.'}


def dbb_tactical_excerpt(text):
    """Preserve the game summary and surrounding sentences for tactical references."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    windows = list(dict.fromkeys(
        ' '.join(sentences[max(0, i - 1):i + 2])
        for i, sentence in enumerate(sentences) if DBB_ACTION.search(sentence)
    ))
    if not windows:
        return text[:6200].rsplit(' ', 1)[0] if len(text) > 6200 else text
    if len(windows) > 8:
        windows = windows[:4] + windows[-4:]
    summary = ' '.join(sentences[:2])[:650]
    return '\n\n[...]\n\n'.join([summary, *(window[:680] for window in windows)])


def dbb_qualifier_passages(html):
    """Read completed senior men's qualifiers from the official DBB team page."""
    soup = BeautifulSoup(html, 'html.parser')
    reports = []
    for card in soup.select('.teaser-post[data-link]'):
        heading = card.select_one('.teaser-post__title')
        body = card.select_one('.teaser-post__excerpt')
        day = card.select_one('.teaser-post__date')
        if not heading or not body or not day:
            continue
        title = heading.get_text(' ', strip=True)
        excerpt = body.get_text(' ', strip=True)
        url = public_source_url(card['data-link'])
        lead = excerpt[:550]
        if (not url or urlsplit(url).hostname != 'www.basketball-bund.de'
                or not DBB_QUALIFIER_TITLE.match(title) or not DBB_GAME_SCORE.search(lead)
                or not DBB_RESULT.search(lead)):
            continue
        try:
            published = datetime.strptime(day.get_text(' ', strip=True), '%d/%m/%Y').date()
        except ValueError:
            continue
        excerpt = dbb_tactical_excerpt(excerpt)
        digest = hashlib.sha256((url + '\n' + excerpt).encode()).hexdigest()[:24]
        reports.append((published, {
            'source_id': 'web-' + digest,
            'title': title,
            'url': url,
            'evidence_url': url,
            'locator': f'DBB match report · published {published.isoformat()}',
            'text': excerpt,
            'kind': 'official_match_report',
        }))
    reports.sort(key=lambda report: report[0], reverse=True)
    return [passage for _, passage in reports[:2]]


async def recent_dbb_qualifiers():
    try:
        async with asyncio.timeout(12), httpx.AsyncClient(timeout=10) as client:
            response = await client.get(DBB_TEAM_URL)
        response.raise_for_status()
        return {'passages': dbb_qualifier_passages(response.content)}
    except (TimeoutError, httpx.HTTPError):
        return {'error': 'The official DBB match reports are temporarily unavailable.'}
