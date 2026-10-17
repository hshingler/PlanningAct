#!/usr/bin/env python3
"""Build a static Planning Act viewer from a Logseq DB-graph EDN export.
Uses only Python's standard library. Tested against Logseq datoms export schema 65.34.
"""
import re, json, sys, html, shutil
from pathlib import Path

DATOM = re.compile(r'^\s*\[(\d+)\s+(:[\w./?!-]+)\s+(.*?)\]\s*$', re.M)

def val(raw):
    raw=raw.strip()
    if raw.startswith('"'):
        try: return json.loads(raw)
        except Exception: return raw[1:-1]
    if raw.startswith('#uuid '): return raw[6:].strip().strip('"')
    if raw in ('true','false'): return raw=='true'
    if raw=='nil': return None
    if re.fullmatch(r'-?\d+',raw): return int(raw)
    if raw.startswith(':'): return raw[1:]
    return raw

def build(src, out):
    text=Path(src).read_text(encoding='utf-8')
    ents={}; refs=[]; tags=[]
    for m in DATOM.finditer(text):
        eid, attr, raw=int(m.group(1)),m.group(2),m.group(3)
        v=val(raw)
        e=ents.setdefault(eid,{"id":eid,"refs":[],"tags":[]})
        if attr==':block/refs': e['refs'].append(v)
        elif attr==':block/tags': e['tags'].append(v)
        else: e[attr[1:]]=v
    # Resolve human names for references and page IDs.
    pages=[]
    for eid,e in ents.items():
        if e.get('block/name') and e.get('block/title'):
            pages.append({"id":eid,"label":e.get('block/title'),"name":e.get('block/name'),"uuid":e.get('block/uuid'),"tags":e.get('tags',[])})
    pages.sort(key=lambda p:p['label'].casefold())
    page_by_id={p['id']:p for p in pages}
    page_by_name={p['name'].casefold():p for p in pages}
    page_by_title={p['label'].casefold():p for p in pages}
    uuid_to_id={str(e.get('block/uuid')):eid for eid,e in ents.items() if e.get('block/uuid')}
    # Page tags are page entities; map direct tag refs to readable titles.
    records=[]
    for eid,e in ents.items():
        if 'block/title' not in e: continue
        pgid=e.get('block/page')
        pg=page_by_id.get(pgid)
        kind='page' if e.get('block/name') else 'block'
        direct_tags=[page_by_id[t]['label'] if t in page_by_id else str(t) for t in e.get('tags',[])]
        page_tags=[page_by_id[t]['label'] for t in (pg or {}).get('tags',[]) if t in page_by_id]
        refs_resolved=[]
        for r in e.get('refs',[]):
            if r in page_by_id: refs_resolved.append({"id":r,"label":page_by_id[r]['label'],"kind":"page"})
            elif r in ents and ents[r].get('block/title'):
                re_=ents[r]; rpg=page_by_id.get(re_.get('block/page'))
                refs_resolved.append({"id":r,"label":re_.get('block/title'),"page":rpg['label'] if rpg else '',"kind":"block"})
        records.append({"id":eid,"uuid":e.get('block/uuid'),"text":e.get('block/title') or '',"name":e.get('block/name'),"kind":kind,"pageId":pgid if pg else (eid if kind=='page' else None),"page":pg['label'] if pg else (e.get('block/title') if kind=='page' else '(unassigned)'),"parentId":e.get('block/parent'),"order":str(e.get('block/order') or ''),"tags":direct_tags,"pageTags":page_tags,"refs":[r['id'] for r in refs_resolved],"resolvedRefs":refs_resolved})
    # Only publish pages with actual content, but keep all page entities for links/navigation.
    payload={"meta":{"source":"Logseq DB graph EDN export","schemaVersion":"65.34","pageCount":len(pages),"recordCount":len(records),"titledBlockCount":sum(1 for r in records if r['text'].strip())},"pages":pages,"records":records}
    out=Path(out); out.mkdir(parents=True,exist_ok=True)
    (out/'data.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    shutil.copyfile(Path(__file__).with_name('index.html'),out/'index.html')
    print(f'Built {out}: {len(pages)} pages, {len(records)} titled records, { (out/"data.json").stat().st_size/1024/1024:.1f} MB data.json')

if __name__=='__main__':
    if len(sys.argv)!=3: print('Usage: python3 build_site.py graph-export.edn output-folder'); sys.exit(2)
    build(sys.argv[1],sys.argv[2])
