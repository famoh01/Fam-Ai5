#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fam Ai ข่าวสด — Live News Server (Python stdlib only, no pip install)
-------------------------------------------------------------------
- เสิร์ฟเว็บไซต์ (ไฟล์ static ในโฟลเดอร์เดียวกับไฟล์นี้)
- /api/news : รวมข่าวสดจริงจาก RSS ของสำนักข่าวไทย อัตโนมัติทุก 5 นาที

วิธีใช้:  python3 server.py   แล้วเปิด http://localhost:8000
"""
import http.server
import socketserver
import urllib.request
import json
import re
import html
import hashlib
import threading
import time
import os
import traceback
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

PORT = int(os.environ.get('PORT', '8000'))
ROOT = os.path.dirname(os.path.abspath(__file__))
TTL = 300  # cache 5 นาที
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0 Safari/537.36 FamAiNews/1.0')

# (ชื่อสำนักข่าว, รหัส, URL RSS, สีประจำแบรนด์)
FEEDS = [
    ('ข่าวสด',            'khaosod',   'https://www.khaosod.co.th/feed',   '#e11d2e'),
    ('มติชน',             'matichon',  'https://www.matichon.co.th/feed',  '#0369a1'),
    ('ประชาชาติธุรกิจ',    'prachachat', 'https://www.prachachat.net/feed',  '#0f766e'),
    ('ข่าวหุ้นธุรกิจ',     'kaohoon',   'https://www.kaohoon.com/feed',     '#ea580c'),
]

NS = {
    'media': 'http://search.yahoo.com/mrss/',
    'content': 'http://purl.org/rss/1.0/modules/content/',
    'dc': 'http://purl.org/dc/elements/1.1/',
}

CACHE = {'items': [], 'updated': 0.0, 'errors': [], 'loading': False}
LOCK = threading.Lock()
BASE_TAGS = ['#ข่าวสด', '#FamAi', '#ข่าววันนี้', '#BreakingNews', '#ทันทุกข่าว',
             '#ข่าวออนไลน์', '#ประเด็นร้อน', '#อัปเดตล่าสุด', '#เกาะติดสถานการณ์', '#สำนักข่าวFamAi']


def strip_html(s):
    s = re.sub(r'<[^>]+>', ' ', s or '')
    s = html.unescape(s)
    return re.sub(r'\s+', ' ', s).strip()


def find_image(item, desc, content):
    for tag in ('media:thumbnail', 'media:content'):
        for n in item.findall(tag, NS):
            url = n.get('url') or ''
            typ = (n.get('type') or '').lower()
            if url and (typ.startswith('image') or re.search(r'\.(jpg|jpeg|png|webp|gif)(\?|$)', url, re.I) or not typ):
                if not re.search(r'\.(mp4|mp3|avi|mov)(\?|$)', url, re.I):
                    return url
    for enc in item.findall('enclosure'):
        url = enc.get('url') or ''
        typ = (enc.get('type') or '').lower()
        if url and typ.startswith('image'):
            return url
    for blob in (desc, content):
        m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', blob or '')
        if m:
            return m.group(1)
    return None


def auto_tags(source, category, title):
    tags = list(BASE_TAGS)
    tags.append('#' + re.sub(r'\s+', '', source))
    cat = re.sub(r'\s+', '', category or '')
    if cat and len(cat) <= 18:
        tags.append('#' + cat)
    return tags[:12]


def parse_feed(name, key, url, color):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    items = []
    for it in root.iter('item'):
        title = strip_html(it.findtext('title') or '')
        link = (it.findtext('link') or '').strip()
        if not title:
            continue
        desc = it.findtext('description') or ''
        content = it.findtext('content:encoded', default='', namespaces=NS) or ''
        pub = it.findtext('pubDate') or it.findtext('dc:date', default='', namespaces=NS) or ''
        category = strip_html(it.findtext('category') or '') or 'ข่าว'
        iso = ''
        try:
            dt = parsedate_to_datetime(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            iso = dt.isoformat()
        except Exception:
            iso = pub if 'T' in pub else ''

        excerpt = strip_html(desc or content)
        body = strip_html(content or desc)
        items.append({
            'id': 'live-' + hashlib.md5((link or title).encode('utf-8')).hexdigest()[:10],
            'title': title,
            'link': link,
            'excerpt': excerpt[:220] + ('…' if len(excerpt) > 220 else ''),
            'body': body[:700],
            'category': category[:24],
            'source': name,
            'sourceColor': color,
            'image': find_image(it, desc, content),
            'time': iso,
            'breaking': False,
            'pinned': False,
            'tags': auto_tags(name, category, title),
        })
    return items


def refresh_cache():
    errors = []
    collected = {}
    def grab(feed):
        name, key, url, color = feed
        try:
            collected[key] = parse_feed(*feed)
        except Exception as e:
            collected[key] = []
            errors.append('%s: %s' % (name, e))
    threads = [threading.Thread(target=grab, args=(f,)) for f in FEEDS]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=25)
    all_items = []
    for f in FEEDS:
        all_items.extend(collected.get(f[1], []))
    all_items.sort(key=lambda x: x.get('time') or '', reverse=True)
    with LOCK:
        CACHE['items'] = all_items[:80]
        CACHE['updated'] = time.time()
        CACHE['errors'] = errors
        CACHE['loading'] = False
    print('[FamAi] refreshed: %d items, %d errors' % (len(all_items), len(errors)))


def api_news():
    if time.time() - CACHE['updated'] > TTL and not CACHE['loading']:
        with LOCK:
            CACHE['loading'] = True
        refresh_cache()
    with LOCK:
        return {
            'ok': True,
            'updated': CACHE['updated'],
            'updatedText': datetime.now().strftime('%H:%M น.'),
            'count': len(CACHE['items']),
            'errors': CACHE['errors'],
            'sources': [{'name': f[0], 'key': f[1], 'color': f[3]} for f in FEEDS],
            'items': CACHE['items'],
        }


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        if self.path.split('?')[0] == '/api/news':
            try:
                self.send_json(api_news())
            except Exception:
                traceback.print_exc()
                self.send_json({'ok': False, 'items': [], 'error': 'internal error'}, 500)
            return
        if self.path.split('?')[0] == '/api/refresh':
            with LOCK:
                CACHE['updated'] = 0.0
            self.send_json(api_news())
            return
        super().do_GET()

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == '__main__':
    print('=' * 60)
    print('Fam Ai ข่าวสด — LIVE NEWS SERVER')
    print('เปิดเว็บที่  http://localhost:%d' % PORT)
    print('API ข่าวสด   http://localhost:%d/api/news' % PORT)
    print('ฟีดที่ดึง: ' + ', '.join(f[0] for f in FEEDS))
    print('=' * 60)
    threading.Thread(target=refresh_cache, daemon=True).start()
    ThreadingServer(('0.0.0.0', PORT), Handler).serve_forever()
