#!/usr/bin/env python3
"""Safety headlines for the AutoTQ industry pages.

Reads the publishers' own feeds listed in sources.json (trade and safety publications, safety agencies), keeps the
items that are about safety in each industry, and writes one small JSON file per industry. The pages show the
headline, the publisher and the date, and link out to the publisher. No article text is copied.

    python fetch.py --out docs              docs/<industry>.json (what the site reads)
    python fetch.py --snapshot file.json    one file with every industry (what the site build bakes into the pages)
    python fetch.py --show                  print what was kept and why the rest was dropped

A news API can widen the net: set NEWS_API_PROVIDER (thenewsapi, currents, gnews, newsdata or newsapi) and
NEWS_API_KEY in the environment and its results go through the same rules. The key is read from the environment
only and is never written to a file. Without a key the feeds alone are used.

Standard library only, so it runs anywhere Python 3.9+ does."""
import argparse, concurrent.futures, datetime, email.utils, html, json, os, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
UA = 'Mozilla/5.0 (compatible; AutoTQ-news/1.0; +https://www.theautotq.com/)'
UTC = datetime.timezone.utc
TAG = re.compile(r'<[^>]+>')


def get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=dict({'User-Agent': UA, 'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml, */*'}, **(headers or {})))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(6_000_000)


def when(s):
    """a feed date (RFC 822 or ISO 8601) as an aware datetime, or None"""
    s = (s or '').strip()
    if not s:
        return None
    try:
        t = email.utils.parsedate_to_datetime(s)
    except Exception:
        t = None
    if t is None:
        try:
            t = datetime.datetime.fromisoformat(s.replace('Z', '+00:00'))
        except Exception:
            return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def clean(s):
    s = html.unescape(html.unescape(TAG.sub(' ', s or '')))
    return re.sub(r'\s+', ' ', s).strip()


def local(tag):
    return tag.rsplit('}', 1)[-1].lower()


def parse(raw):
    """items of an RSS or Atom document as (title, link, date)"""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        text = raw.decode('utf-8', 'replace')
        out = []
        for block in re.findall(r'<item\b.*?</item>|<entry\b.*?</entry>', text, flags=re.S | re.I):
            g = lambda t: (re.search(r'<%s\b[^>]*>(.*?)</%s>' % (t, t), block, flags=re.S | re.I) or [None, ''])[1]
            cd = lambda v: re.sub(r'^\s*<!\[CDATA\[(.*?)\]\]>\s*$', r'\1', v, flags=re.S)
            link = cd(g('link')) or (re.search(r'<link\b[^>]*href="([^"]+)"', block, flags=re.I) or [None, ''])[1]
            out.append((clean(cd(g('title'))), link.strip(), when(cd(g('pubDate')) or cd(g('updated')) or cd(g('published')) or cd(g('dc:date')))))
        return out
    out = []
    for el in root.iter():
        if local(el.tag) not in ('item', 'entry'):
            continue
        title = link = date = ''
        for c in el:
            n = local(c.tag)
            if n == 'title' and not title:
                title = ''.join(c.itertext())
            elif n == 'link' and not link:
                link = (c.text or '').strip() or (c.get('href') if c.get('rel') in (None, 'alternate') else '') or ''
            elif n in ('pubdate', 'published', 'updated', 'date') and not date:
                date = c.text or ''
        out.append((clean(title), link.strip(), when(date)))
    return out


def host(url):
    return urllib.parse.urlsplit(url).netloc.lower().removeprefix('www.')


def api_items(cfg, key, ind):
    """results of the optional news API for one industry, as (source name, title, link, date); [] without a key"""
    prov, tok = os.environ.get('NEWS_API_PROVIDER', '').strip().lower(), os.environ.get('NEWS_API_KEY', '').strip()
    if not prov or not tok:
        return []
    q = ind['query']
    doms = ','.join(sorted({host(f['url']) for f in ind['feeds']}))
    enc = urllib.parse.urlencode
    try:
        if prov == 'thenewsapi':
            j = json.loads(get('https://api.thenewsapi.com/v1/news/all?' + enc({'api_token': tok, 'search': q.replace(' ', ' | '), 'language': 'en', 'sort': 'published_at', 'limit': 25, 'domains': doms})))
            return [(a.get('source') or host(a.get('url', '')), a.get('title'), a.get('url'), when(a.get('published_at'))) for a in j.get('data', [])]
        if prov == 'currents':
            j = json.loads(get('https://api.currentsapi.services/v1/search?' + enc({'keywords': q, 'language': 'en', 'country': 'US'}), {'Authorization': tok}))
            return [(host(a.get('url', '')), a.get('title'), a.get('url'), when((a.get('published') or '').replace(' +0000', '+00:00').replace(' ', 'T', 1))) for a in j.get('news', [])]
        if prov == 'gnews':
            j = json.loads(get('https://gnews.io/api/v4/search?' + enc({'q': q, 'lang': 'en', 'country': 'us', 'max': 10, 'sortby': 'publishedAt', 'apikey': tok})))
            return [((a.get('source') or {}).get('name') or host(a.get('url', '')), a.get('title'), a.get('url'), when(a.get('publishedAt'))) for a in j.get('articles', [])]
        if prov == 'newsdata':
            j = json.loads(get('https://newsdata.io/api/1/latest?' + enc({'apikey': tok, 'q': q, 'language': 'en', 'country': 'us'})))
            return [(a.get('source_name') or host(a.get('link', '')), a.get('title'), a.get('link'), when((a.get('pubDate') or '').replace(' ', 'T', 1))) for a in j.get('results', [])]
        if prov == 'newsapi':
            j = json.loads(get('https://newsapi.org/v2/everything?' + enc({'q': q, 'language': 'en', 'sortBy': 'publishedAt', 'pageSize': 30, 'domains': doms}), {'X-Api-Key': tok}))
            return [((a.get('source') or {}).get('name') or host(a.get('url', '')), a.get('title'), a.get('url'), when(a.get('publishedAt'))) for a in j.get('articles', [])]
        print('unknown NEWS_API_PROVIDER:', prov, file=sys.stderr)
    except Exception as e:                                  # the feeds still stand when the API does not answer
        print('news API (%s) did not answer for %s: %s' % (prov, key, type(e).__name__), file=sys.stderr)
    return []


def run(cfg, now=None, log=None):
    now = now or datetime.datetime.now(UTC)
    urls = sorted({f['url'] for f in cfg['cross']} | {f['url'] for i in cfg['industries'].values() for f in i['feeds']})
    raw = {}

    def fetch(u):
        err = None
        for wait in (0, 3, 8):                              # a feed that fails once often answers a few seconds later
            time.sleep(wait)
            try:
                return u, parse(get(u))
            except Exception as e:
                err = e
        return u, err
    with concurrent.futures.ThreadPoolExecutor(6) as ex:
        for u, r in ex.map(fetch, urls):
            raw[u] = r
            if not isinstance(r, list):
                print('feed did not answer: %s (%s)' % (u, type(r).__name__), file=sys.stderr)
            if log is not None:
                log.append('feed %-90s %s' % (u[:90], ('%d items' % len(r)) if isinstance(r, list) else 'FAILED %s' % type(r).__name__))
    block, calm, soft = (re.compile(cfg[k], re.I) for k in ('block', 'calm', 'soft'))
    out = {}
    for key, ind in cfg['industries'].items():
        about = re.compile(ind['about'], re.I)
        safety = re.compile(cfg['safety'] + ('|' + ind['safety_extra'] if ind.get('safety_extra') else ''), re.I)
        oldest = now - datetime.timedelta(days=ind.get('window_days', cfg['window_days']))
        pool, seen = [], set()
        feeds = ind['feeds'] + (cfg['cross'] if ind.get('cross') else [])
        rows = [(f['name'], f['gate'], it) for f in feeds for it in (raw.get(f['url']) if isinstance(raw.get(f['url']), list) else [])]
        rows += [(n, 'both', (clean(t), l, d)) for n, t, l, d in api_items(cfg, key, ind)]
        for name, gate, (title, link, date) in rows:
            why = None
            if not title or not (24 <= len(title) <= 170): why = 'length'
            elif not (link or '').startswith('https://'): why = 'link'
            elif date is None or not (oldest <= date <= now + datetime.timedelta(days=1)): why = 'date'
            elif gate in ('about', 'both') and not about.search(title): why = 'not about this industry'
            elif gate in ('safety', 'both') and not safety.search(title): why = 'not about safety'
            elif block.search(title): why = 'blocked word'
            elif ind.get('calm') and calm.search(title): why = 'incident wording'
            sig = ' '.join(re.findall(r'[a-z0-9]+', title.lower())[:7])
            if why is None and sig in seen: why = 'duplicate'
            if why is None:
                seen.add(sig)
                pool.append({'title': title, 'url': link, 'source': name, 'date': date.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')})
            elif log is not None and why not in ('date', 'length'):
                log.append('  drop [%s] %-18s %s | %s' % (key, why, name, title[:90]))
        pool.sort(key=lambda i: i['date'], reverse=True)
        picked, per, grim = [], {}, 0
        cap = ind.get('per_source', cfg['per_source'])
        for i in pool:
            hard = bool(soft.search(i['title']))
            if per.get(i['source'], 0) >= cap or (hard and grim >= cfg['soft_max']):
                continue
            per[i['source']] = per.get(i['source'], 0) + 1
            grim += hard
            picked.append(i)
            if len(picked) == cfg['take']:
                break
        out[key] = picked if len(picked) >= cfg['min'] else []
        if log is not None:
            log.append('KEEP [%s] %d of %d that passed' % (key, len(out[key]), len(pool)))
            log.extend('  keep [%s] %s %-28s %s' % (key, i['date'][:10], i['source'][:28], i['title'][:100]) for i in picked)
    return {'fetched': now.strftime('%Y-%m-%dT%H:%M:%SZ'), 'industries': out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out'); ap.add_argument('--snapshot'); ap.add_argument('--show', action='store_true')
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(HERE, 'sources.json'), encoding='utf-8'))
    log = [] if a.show else None
    res = run(cfg, log=log)
    if a.show:
        sys.stdout.reconfigure(encoding='utf-8')
        print('\n'.join(log))
    if a.snapshot:
        if os.path.exists(a.snapshot):                      # a bad day at the sources must not wipe a good list
            old = json.load(open(a.snapshot, encoding='utf-8')).get('industries', {})
            for key, items in res['industries'].items():
                if not items and old.get(key):
                    res['industries'][key] = old[key]
                    print('kept the earlier list for %s: nothing passed this time' % key, file=sys.stderr)
        json.dump(res, open(a.snapshot, 'w', encoding='utf-8', newline='\n'), indent=1, ensure_ascii=False)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        for key, items in res['industries'].items():
            path = os.path.join(a.out, key + '.json')
            if os.path.exists(path):
                if not items:
                    continue                                # a bad day at the sources must not wipe a good list: the page ages it out by itself
                try:
                    if json.load(open(path, encoding='utf-8')).get('items') == items:
                        continue                            # nothing new: the file stays as it is, so the history shows real changes only
                except Exception:
                    pass
            json.dump({'industry': key, 'updated': res['fetched'], 'items': items}, open(path, 'w', encoding='utf-8', newline='\n'), ensure_ascii=False)
    print('fetched %s | %s' % (res['fetched'], ', '.join('%s %d' % (k, len(v)) for k, v in res['industries'].items())))


if __name__ == '__main__':
    main()
