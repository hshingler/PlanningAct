#!/usr/bin/env python3
"""Build a static prototype from a Logseq database EDN export.

Usage: python build.py input.edn output-directory
The source export is read-only; output is written to a separate directory.
"""
import ast, collections, html, json, os, re, shutil, sys, unicodedata
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit('Usage: python build.py input.edn output-directory')
src, out = Path(sys.argv[1]), Path(sys.argv[2])
text = src.read_text(encoding='utf-8')
# Datoms are emitted one per line by Logseq. This captures multiline EDN values
# while requiring each datom's closing bracket to be at the end of its line.
pat = re.compile(r'^\s*\[(\d+)\s+:([^\s]+)\s+(.*?)\]\s*$', re.M | re.S)
entities = collections.defaultdict(lambda: collections.defaultdict(list))

def parse_value(raw):
    raw = raw.strip()
    if raw.startswith('"'):
        try: return ast.literal_eval(raw)
        except Exception: return raw[1:-1]
    if raw.startswith('#uuid '): return raw[6:].strip().strip('"')
    if raw == 'true': return True
    if raw == 'false': return False
    if re.fullmatch(r'-?\d+', raw): return int(raw)
    if raw.startswith(':'): return raw[1:]
    return raw

count = 0
for m in pat.finditer(text):
    eid, attr, raw = int(m.group(1)), m.group(2), m.group(3)
    entities[eid][attr].append(parse_value(raw)); count += 1
if count < 1000:
    raise SystemExit(f'Could not parse EDN export reliably (only {count} datoms).')

def one(attrs, key, default=None):
    vals = attrs.get(key)
    return vals[0] if vals else default

def slugify(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii').lower()
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:90] or 'page'

pages = {}
for eid, attrs in entities.items():
    name = one(attrs, 'block/name')
    title = one(attrs, 'block/title')
    if isinstance(name, str) and isinstance(title, str):
        pages[eid] = {'id': eid, 'name': name, 'title': title,
                      'uuid': one(attrs, 'block/uuid', ''),
                      'tags': attrs.get('block/tags', []),
                      'refs': attrs.get('block/refs', [])}
# Stable unique page filenames
used = collections.Counter()
for p in sorted(pages.values(), key=lambda x: x['id']):
    base = slugify(p['title']); used[base] += 1
    p['slug'] = base if used[base] == 1 else f"{base}-{p['id']}"
page_by_id = pages
page_by_uuid = {p['uuid']: p for p in pages.values() if p['uuid']}
entity_by_uuid = {}
for eid, attrs in entities.items():
    uid = one(attrs, 'block/uuid')
    if uid: entity_by_uuid[uid] = (eid, attrs)

# Build page hierarchy and stable block anchors.
children = collections.defaultdict(list)
block_info = {}
for eid, attrs in entities.items():
    if eid in pages: continue
    title = one(attrs, 'block/title')
    if not isinstance(title, str): continue
    page_id = one(attrs, 'block/page')
    parent = one(attrs, 'block/parent')
    if isinstance(page_id, int) and page_id in pages:
        info = {'id': eid, 'title': title, 'page_id': page_id,
                'parent': parent if isinstance(parent, int) else page_id,
                'uuid': one(attrs, 'block/uuid', ''),
                'order': str(one(attrs, 'block/order', '')),
                'tags': attrs.get('block/tags', []),
                'refs': attrs.get('block/refs', [])}
        block_info[eid] = info
        children[info['parent']].append(eid)

def order_key(eid):
    b = block_info[eid]
    return (b['order'], eid)
for par in children: children[par].sort(key=order_key)
block_by_uuid = {b['uuid']: b for b in block_info.values() if b['uuid']}

# Build incoming links from Logseq's saved :block/refs datoms.
page_blocks = collections.defaultdict(set)
for bid, b in block_info.items():
    page_blocks[b['page_id']].add(bid)
incoming_linked = collections.defaultdict(dict)
for source_id, attrs in entities.items():
    refs = {r for r in attrs.get('block/refs', []) if isinstance(r, int)}
    if not refs:
        continue
    if source_id in pages:
        source = {'kind':'page','id':source_id,'page_id':source_id,'title':pages[source_id]['title'],'uuid':pages[source_id]['uuid'],'text':pages[source_id]['title']}
    elif source_id in block_info:
        b = block_info[source_id]
        source = {'kind':'block','id':source_id,'page_id':b['page_id'],'title':b['title'],'uuid':b['uuid'],'text':b['title']}
    else:
        continue
    for target_page_id in pages:
        targets = {target_page_id} | page_blocks.get(target_page_id, set())
        if refs.intersection(targets) and source['page_id'] != target_page_id:
            incoming_linked[target_page_id][source_id] = source

# Candidate unlinked references: page titles mentioned in blocks without a saved link.
short_acronyms = {'RSP','LUP','NEP','NPD','NES','NPS'}
stop_titles = {'root tag','tag','property','page','template','favorites','heading','quote','state','file type','external url','published url','table view pinned columns','annotation image'}
target_patterns = []
for target in pages.values():
    title = re.sub(r'\s+', ' ', target['title']).strip()
    if title.casefold() in stop_titles or (len(title) < 4 and title.upper() not in short_acronyms):
        continue
    target_patterns.append((target, re.compile(r'(?<![\w])' + re.escape(title) + r'(?![\w])', re.I)))
unlinked_refs = collections.defaultdict(list)
for bid, b in block_info.items():
    source_text = b['title']
    source_refs = {r for r in entities[bid].get('block/refs', []) if isinstance(r, int)}
    if not source_text:
        continue
    for target, pattern in target_patterns:
        if b['page_id'] == target['id'] or source_refs.intersection({target['id']} | page_blocks.get(target['id'], set())):
            continue
        match = pattern.search(source_text)
        if match:
            start, end = match.span()
            excerpt = source_text[max(0,start-100):min(len(source_text),end+140)]
            if start > 100: excerpt = '…' + excerpt
            if end + 140 < len(source_text): excerpt += '…'
            unlinked_refs[target['id']].append({'kind':'block','id':bid,'page_id':b['page_id'],'title':source_text,'uuid':b['uuid'],'text':excerpt})

def render_links(s, prefix=""):
    # Replace Logseq UUID links with placeholders before escaping all source text.
    # This preserves links while ensuring arbitrary exported content is not treated as HTML.
    links = []
    def hold(label, uid):
        target = resolve_uuid(uid)
        if not target:
            return html.escape(label)
        token = f"LOGSEQLINKTOKEN{len(links)}END"
        links.append((token, f'<a href="{html.escape(prefix + target, quote=True)}">{html.escape(label)}</a>'))
        return token
    def labeled(m): return hold(m.group(1), m.group(2))
    s = re.sub(r'\[([^\]]+)\]\(\[\[([0-9a-fA-F-]{36})\]\]\)', labeled, s)
    def bare(m):
        uid = m.group(1)
        if uid in page_by_uuid: label = page_by_uuid[uid]['title']
        elif uid in block_by_uuid: label = block_by_uuid[uid]['title']
        else: label = uid
        return hold(label, uid)
    s = re.sub(r'\[\[([0-9a-fA-F-]{36})\]\]', bare, s)
    s = html.escape(s)
    # Restore trusted, escaped anchors after escaping the remaining source text.
    for token, anchor in links:
        s = s.replace(token, anchor)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', s)
    s = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', s)
    return s

def resolve_uuid(uid):
    if uid in page_by_uuid: return f"{page_by_uuid[uid]['slug']}.html"
    if uid in block_by_uuid:
        b = block_by_uuid[uid]; return f"{pages[b['page_id']]['slug']}.html#block-{b['uuid']}"
    return None

def clean_text(s):
    return re.sub(r'\s+', ' ', s).strip()

def reference_href(ref, from_root=False):
    prefix = 'pages/' if from_root else ''
    if ref['kind'] == 'page':
        return prefix + pages[ref['page_id']]['slug'] + '.html'
    b = block_info.get(ref['id'])
    if not b:
        return prefix + pages[ref['page_id']]['slug'] + '.html'
    return prefix + pages[b['page_id']]['slug'] + '.html#block-' + (b['uuid'] or f'id-{b["id"]}')

def reference_panel(title, items, from_root=False, max_items=100):
    total = len(items)
    if not items:
        return f'<details class="reference-panel"><summary>{html.escape(title)} <span class="ref-count">0</span></summary><div class="ref-empty">No {html.escape(title.lower())} found in this export.</div></details>'
    ordered = sorted(items, key=lambda r: (pages[r['page_id']]['title'].casefold(), r['title'].casefold()))
    rows = []
    for ref in ordered[:max_items]:
        source_title = pages[ref['page_id']]['title']
        href = reference_href(ref, from_root)
        excerpt = ref.get('text', ref['title'])
        rows.append(f'<li class="reference-item"><a href="{html.escape(href, quote=True)}">{html.escape(source_title)}</a><p>{html.escape(excerpt)}</p></li>')
    more = f'<p class="ref-source">Showing {min(total,max_items)} of {total} references.</p>' if total > max_items else ''
    return f'<details class="reference-panel"><summary>{html.escape(title)} <span class="ref-count">{total}</span></summary><ul class="reference-list">{"".join(rows)}</ul>{more}</details>'

def render_block(eid, seen, depth=0, prefix=""):
    if eid in seen or eid not in block_info: return ''
    seen.add(eid); b = block_info[eid]
    uid = b['uuid'] or f'id-{eid}'
    title_html = render_links(b['title'], prefix)
    # Preserve the hierarchy without inventing statutory semantics.
    tag_labels = [pages[t]['title'] if t in pages else str(t) for t in b['tags']]
    tag_html = ''.join(f'<span class="tag">{html.escape(str(t))}</span>' for t in tag_labels if t)
    kids = ''.join(render_block(k, seen, depth+1, prefix) for k in children.get(eid, []))
    return f'<li id="block-{html.escape(uid)}"><div class="block-text">{title_html}</div>{("<div class=\"tags\">"+tag_html+"</div>") if tag_html else ""}{("<ul>"+kids+"</ul>") if kids else ""}</li>'

if out.exists(): shutil.rmtree(out)
(out / 'pages').mkdir(parents=True)
(out / 'assets').mkdir()
css = r'''*{box-sizing:border-box}body{margin:0;background:#f7f7f5;color:#202522;font:16px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:#175d50;text-decoration-thickness:1px;text-underline-offset:3px}a:hover{color:#0b3b32}.wrap{max-width:1100px;margin:auto;padding:28px 22px}.top{background:#173f37;color:white}.top a{color:white}.brand{font-weight:750;letter-spacing:.01em;font-size:1.1rem}.hero{padding:28px 0 34px}.hero h1{font-size:clamp(2rem,5vw,3.4rem);line-height:1.05;margin:.5rem 0 1rem;max-width:780px}.hero p{max-width:720px;color:#e0ebe6}.search{display:flex;gap:8px;margin:22px 0 8px;max-width:780px}.search input{flex:1;min-width:0;padding:14px;border:1px solid #cbd4cf;border-radius:8px;font:inherit}.search button,.button{padding:12px 16px;border:0;border-radius:8px;background:#d6e8df;color:#173f37;font-weight:650;cursor:pointer}.layout{display:grid;grid-template-columns:240px minmax(0,1fr);gap:28px}.panel,.content-card{background:white;border:1px solid #e1e5e1;border-radius:12px;padding:18px}.panel h2,.content-card h2{margin-top:0}.navlist{padding:0;list-style:none}.navlist li{margin:.55rem 0}.muted{color:#65716b}.small{font-size:.88rem}.results{display:grid;gap:10px;margin-top:14px}.result{background:white;border:1px solid #e1e5e1;border-radius:10px;padding:14px}.result h3{margin:0 0 4px;font-size:1rem}.result p{margin:.35rem 0}.pill,.tag{display:inline-block;background:#eef2ef;color:#47544d;border-radius:99px;padding:2px 8px;font-size:.78rem;margin:2px 4px 2px 0}.crumb{font-size:.88rem;color:#65716b;margin-bottom:12px}.page-title{font-size:clamp(1.8rem,4vw,2.5rem);line-height:1.15;margin:.2rem 0 1rem}.page-tree{padding-left:1.35rem}.page-tree>li{padding:.25rem 0}.page-tree ul{padding-left:1.4rem;margin:.35rem 0}.block-text{white-space:pre-wrap;overflow-wrap:anywhere}.tags{margin-top:5px}.empty{padding:18px;border:1px dashed #cbd4cf;border-radius:10px;color:#65716b}.footer{margin-top:42px;padding-top:18px;border-top:1px solid #dce2dd;color:#65716b;font-size:.85rem}.notice{background:#fff7e7;border-left:4px solid #c78a24;padding:12px 14px;border-radius:4px;font-size:.92rem;margin:18px 0}.reference-panels{display:grid;grid-template-columns:1fr;gap:12px;margin-top:18px}.reference-panel{background:white;border:1px solid #e1e5e1;border-radius:12px;padding:0 16px}.reference-panel summary{cursor:pointer;font-weight:700;padding:15px 0}.reference-panel .ref-count{display:inline-block;background:#eef2ef;border-radius:99px;padding:1px 8px;font-size:.8rem;margin-left:6px}.reference-list{list-style:none;padding:0;margin:0 0 16px}.reference-item{border-top:1px solid #edf0ed;padding:12px 0}.reference-item p{margin:5px 0 0;color:#65716b;font-size:.92rem;overflow-wrap:anywhere}.ref-source{font-size:.84rem;color:#65716b}.section-heading{margin:28px 0 12px}.home-content{margin-top:18px}.ref-empty{color:#65716b;padding:0 0 15px;font-size:.92rem}@media(max-width:760px){.layout{grid-template-columns:1fr}.wrap{padding:20px 15px}.search{flex-direction:column}.search button{width:100%}}'''
(out/'assets'/'style.css').write_text(css, encoding='utf-8')

# Static searchable index. Includes block text so users can find phrases within provisions.
search_records=[]
for p in pages.values():
    block_ids=[]
    seen=set()
    def walk(pid):
        for bid in children.get(pid, []):
            if bid in seen: continue
            seen.add(bid); block_ids.append(bid)
            walk(bid)
    walk(p['id'])
    body=' '.join(block_info[bid]['title'] for bid in block_ids)
    tags=[pages[t]['title'] if t in pages else str(t) for t in p['tags']]
    search_records.append({'title':p['title'],'slug':p['slug'],'name':p['name'],'tags':tags,'text':clean_text(body)[:50000]})
(out/'assets'/'search-index.json').write_text(json.dumps(search_records, ensure_ascii=False), encoding='utf-8')

# Build each page with the nested graph content and expandable references.
for p in pages.values():
    seen=set()
    tree=''.join(render_block(bid, seen) for bid in children.get(p['id'], []))
    tag_labels=[pages[t]['title'] if t in pages else str(t) for t in p['tags']]
    tags=''.join(f'<span class="tag">{html.escape(str(t))}</span>' for t in tag_labels if t)
    refs_html = '<section class="reference-panels"><h2 class="section-heading">References and connections</h2>' + reference_panel('Linked references', list(incoming_linked.get(p['id'], {}).values())) + reference_panel('Unlinked references', unlinked_refs.get(p['id'], [])) + '</section>'
    body = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(p['title'])} · Planning Act Knowledge Base</title><link rel="stylesheet" href="../assets/style.css"></head><body><header class="top"><div class="wrap"><a class="brand" href="../index.html">Planning Act Knowledge Base</a></div></header><main class="wrap"><div class="crumb"><a href="../index.html">Home</a> / Knowledge graph</div><h1 class="page-title">{html.escape(p['title'])}</h1><div class="tags">{tags}</div><div class="notice">Linked references reflect saved graph links. Unlinked references are candidate title matches and may need review. This prototype is not a verified legal publication.</div><section class="content-card"><ul class="page-tree">{tree or '<li class="muted">No child blocks were found for this page.</li>'}</ul></section>{refs_html}<div class="footer">Generated from the supplied Logseq EDN export. Confirm statutory wording and context against official legislation.</div></main></body></html>'''
    (out/'pages'/f"{p['slug']}.html").write_text(body, encoding='utf-8')

# Browse landing pages use existing Logseq tag associations, not keyword inference.
def page_tag_names(p):
    return [pages[t]['title'] if t in pages else str(t) for t in p['tags']]
def has_tag(p, *labels):
    wanted = {x.casefold() for x in labels}
    return any(str(t).casefold() in wanted for t in page_tag_names(p))

browse_categories = [
    {'slug':'provisions','title':'Provisions','description':'Browse provision pages and statutory material already tagged as provisions in the Logseq graph. Some statutory pages may need additional classification.', 'items':[p for p in pages.values() if has_tag(p,'provision')]},
    {'slug':'concepts-expressions','title':'Concepts and expressions','description':'Explore pages tagged as concepts, then follow their links to the provisions where they appear. A future pass can distinguish defined terms from broader concepts and expressions.', 'items':[p for p in pages.values() if has_tag(p,'concept')]},
    {'slug':'planning-instruments','title':'Planning instruments','description':'Navigate pages associated with RSP, LUP and NEP. A page may relate to more than one instrument; the labels below reflect existing graph tags, not an independent legal conclusion.', 'items':[p for p in pages.values() if has_tag(p,'RSP','LUP','NEP','instrument')]},
    {'slug':'actors','title':'Actors','description':'Find pages already tagged as actors and follow links to the provisions associated with their roles, powers and duties.', 'items':[p for p in pages.values() if has_tag(p,'Actor')]},
]
for cat in browse_categories:
    if cat['slug']=='planning-instruments':
        sub = ''.join(f'<h2>{label}</h2><ul class="navlist">'+''.join(f'<li><a href="pages/{p["slug"]}.html">{html.escape(p["title"])}</a></li>' for p in sorted([p for p in cat['items'] if has_tag(p,label)],key=lambda x:x['title'].casefold()))+'</ul>' for label in ('RSP','LUP','NEP'))
        list_html = sub + '<h2>Other instrument-tagged pages</h2><ul class="navlist">' + ''.join(f'<li><a href="pages/{p["slug"]}.html">{html.escape(p["title"])}</a></li>' for p in sorted([p for p in cat['items'] if not has_tag(p,'RSP','LUP','NEP')],key=lambda x:x['title'].casefold())) + '</ul>'
    else:
        list_html = '<ul class="navlist">' + ''.join(f'<li><a href="pages/{p["slug"]}.html">{html.escape(p["title"])}</a></li>' for p in sorted(cat['items'],key=lambda x:x['title'].casefold())) + '</ul>'
    page_html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(cat['title'])} · Planning Act Knowledge Base</title><link rel="stylesheet" href="assets/style.css"></head><body><header class="top"><div class="wrap"><a class="brand" href="index.html">Planning Act Knowledge Base</a></div></header><main class="wrap"><div class="crumb"><a href="index.html">Home</a> / Browse</div><h1 class="page-title">{html.escape(cat['title'])}</h1><p>{html.escape(cat['description'])}</p><div class="notice">These lists use existing Logseq tags as a starting point. They are not a complete or verified classification of the legislation.</div><section class="content-card"><p class="muted small">{len(cat['items'])} matching pages</p>{list_html}</section><div class="footer"><a href="index.html">Return to search</a></div></main></body></html>'''
    (out/f"{cat['slug']}.html").write_text(page_html,encoding='utf-8')

# Homepage: use the existing Logseq page whose title identifies it as the Planning Act home page.
def is_home_page(p):
    normalized = re.sub(r'[^a-z0-9]+', ' ', p['title'].casefold()).strip()
    return 'planning act' in normalized and 'home' in normalized
home_page = next((p for p in pages.values() if is_home_page(p)), None)
home_tree = ''
home_tags = ''
home_refs = ''
if home_page:
    seen=set()
    home_tree=''.join(render_block(bid, seen, prefix='pages/') for bid in children.get(home_page['id'], []))
    home_tags=''.join(f'<span class="tag">{html.escape(str(pages[t]["title"] if t in pages else t))}</span>' for t in home_page['tags'])
    home_refs='<section class="reference-panels"><h2 class="section-heading">References and connections</h2>'+reference_panel('Linked references',list(incoming_linked.get(home_page['id'],{}).values()),True)+reference_panel('Unlinked references',unlinked_refs.get(home_page['id'],[]),True)+'</section>'
page_list=''.join(f'<li><a href="pages/{p["slug"]}.html">{html.escape(p["title"])}</a></li>' for p in sorted(pages.values(),key=lambda x:x['title'].casefold()))
root_title = home_page['title'] if home_page else 'Planning Act Knowledge Base'
index_html='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ROOT_TITLE · Planning Act Knowledge Base</title><link rel="stylesheet" href="assets/style.css"></head><body><header class="top"><div class="wrap"><div class="brand">Planning Act Knowledge Base</div><section class="hero"><p class="small">Planning Act knowledge graph</p><h1>ROOT_TITLE</h1><p>Your existing Logseq home page, connected to searchable statutory content and graph references.</p><form class="search" id="search-form"><input id="q" type="search" placeholder="Search provisions, concepts, expressions or actors…" aria-label="Search"><button type="submit">Search</button></form><p class="small">Search runs in your browser against the generated index.</p></section></div></header><main class="wrap"><div class="layout"><aside class="panel"><h2>Explore the graph</h2><ul class="navlist"><li><a href="provisions.html"><strong>Provisions</strong></a><div class="muted small">Statutory pages and text</div></li><li><a href="concepts-expressions.html"><strong>Concepts and expressions</strong></a><div class="muted small">Concept pages and linked provisions</div></li><li><a href="planning-instruments.html"><strong>Planning instruments</strong></a><div class="muted small">RSP · LUP · NEP</div></li><li><a href="actors.html"><strong>Actors</strong></a><div class="muted small">Roles, powers and duties</div></li></ul><p><a href="#all-pages">View all pages ↓</a></p><div class="notice">Linked references use saved graph relationships. Unlinked references are candidate title matches, not confirmed legal relationships.</div></aside><section><div id="search-status" class="muted">Loading search index…</div><div id="results" class="results"></div><section class="content-card home-content"><h2>Planning Act home page content</h2><div class="tags">HOME_TAGS</div><ul class="page-tree">HOME_TREE</ul></section>HOME_REFS<section id="all-pages" class="content-card" style="margin-top:18px"><h2>All pages <span class="pill">PAGE_COUNT</span></h2><ul class="navlist">PAGE_LIST</ul></section></section></div><div class="footer">Generated from your Logseq EDN export. Verify statutory wording against official legislation.</div></main><script>
let records=[];const form=document.getElementById('search-form'),input=document.getElementById('q'),results=document.getElementById('results'),status=document.getElementById('search-status');
fetch('assets/search-index.json').then(r=>r.json()).then(d=>{records=d;status.textContent=`Ready to search ${records.length.toLocaleString()} pages.`}).catch(()=>{status.textContent='Could not load the search index. Please rebuild the site.'});
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
form.addEventListener('submit',e=>{e.preventDefault();const q=input.value.trim().toLowerCase();results.innerHTML='';if(!q){status.textContent=`Search ${records.length.toLocaleString()} pages.`;return}const terms=q.split(/\\s+/).filter(Boolean);const hits=records.map(p=>{const hay=(p.title+' '+p.name+' '+p.tags.join(' ')+' '+p.text).toLowerCase();let score=terms.reduce((n,t)=>n+(p.title.toLowerCase().includes(t)?4:0)+(p.tags.join(' ').toLowerCase().includes(t)?2:0)+(p.text.toLowerCase().includes(t)?1:0),0);return {...p,score}}).filter(p=>p.score>0).sort((a,b)=>b.score-a.score||a.title.localeCompare(b.title)).slice(0,100);status.textContent=`${hits.length} matching pages${hits.length===100?' (showing the first 100)':''}.`;if(!hits.length){results.innerHTML='<div class="empty">No matches found. Try a broader phrase or a different spelling.</div>';return}for(const p of hits){const idx=p.text.toLowerCase().indexOf(q);let excerpt='';if(idx>=0){excerpt=p.text.slice(Math.max(0,idx-100),Math.min(p.text.length,idx+q.length+180));if(idx>100)excerpt='…'+excerpt;if(idx+q.length+180<p.text.length)excerpt+='…'}else excerpt=p.text.slice(0,220)+(p.text.length>220?'…':'');const div=document.createElement('article');div.className='result';div.innerHTML=`<h3><a href="pages/${esc(p.slug)}.html">${esc(p.title)}</a></h3><p class="muted small">${p.tags.slice(0,5).map(t=>'<span class="tag">'+esc(t)+'</span>').join('')}</p><p>${esc(excerpt)}</p>`;results.appendChild(div)}});
</script></body></html>'''
index_html=index_html.replace('ROOT_TITLE',html.escape(root_title)).replace('HOME_TAGS',home_tags).replace('HOME_TREE',home_tree or '<li class="muted">No blocks were found on the configured home page.</li>').replace('HOME_REFS',home_refs).replace('PAGE_COUNT',str(len(pages))).replace('PAGE_LIST',page_list)
(out/'index.html').write_text(index_html, encoding='utf-8')

# Manifest helps QA and future build improvements.
manifest={'source_file':src.name,'datoms_parsed':count,'entities':len(entities),'pages':len(pages),'blocks_with_page':len(block_info),'pages_without_children':sum(not children.get(pid) for pid in pages),'generated_files':len(pages)+len(browse_categories)+3,
          'home_page':home_page['title'] if home_page else None,
          'pages_with_linked_references':sum(bool(incoming_linked.get(p['id'])) for p in pages.values()),
          'pages_with_unlinked_references':sum(bool(unlinked_refs.get(p['id'])) for p in pages.values()),
          'linked_reference_edges':sum(len(v) for v in incoming_linked.values()),
          'unlinked_reference_matches':sum(len(v) for v in unlinked_refs.values()),
          'browse_category_counts':{c['title']:len(c['items']) for c in browse_categories},'prototype_notes':['Page and block titles are extracted from :block/title.','Block ordering uses the exported :block/order value.','UUID references are linked when they resolve to an exported page or block.',
          'Linked references are generated from stored :block/refs relationships.',
          'Unlinked references are candidate page-title matches in block text and may include false positives.','This is an initial structural prototype, not a validated legal publication.']}
(out/'build-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps(manifest,indent=2))
