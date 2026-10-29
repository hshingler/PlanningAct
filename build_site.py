#!/usr/bin/env python3
"""Build a static Planning Act knowledge website from a Logseq EDN datom export.
Usage: python build_site.py input.edn output-directory
"""
import ast, collections, html, json, re, shutil, sys, unicodedata
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit('Usage: python build_site.py input.edn output-directory')
src, out = Path(sys.argv[1]), Path(sys.argv[2])
project_root = Path(__file__).resolve().parent
brand_assets = project_root / 'brand-assets'
text = src.read_text(encoding='utf-8')
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

def clean_text(s): return re.sub(r'\s+', ' ', str(s)).strip()

pages = {}
for eid, attrs in entities.items():
    name, title = one(attrs, 'block/name'), one(attrs, 'block/title')
    if isinstance(name, str) and isinstance(title, str):
        pages[eid] = {'id':eid,'name':name,'title':title,'uuid':one(attrs,'block/uuid',''),
                      'tags':attrs.get('block/tags',[]),'refs':attrs.get('block/refs',[])}
used = collections.Counter()
for p in sorted(pages.values(), key=lambda x:x['id']):
    base=slugify(p['title']); used[base]+=1
    p['slug']=base if used[base]==1 else f"{base}-{p['id']}"
page_by_uuid={p['uuid']:p for p in pages.values() if p['uuid']}
entity_by_uuid={}; entity_title_by_id={}
for eid,attrs in entities.items():
    uid=one(attrs,'block/uuid'); title=one(attrs,'block/title')
    if uid: entity_by_uuid[uid]=(eid,attrs)
    if isinstance(title,str): entity_title_by_id[eid]=title

children=collections.defaultdict(list); block_info={}
for eid,attrs in entities.items():
    if eid in pages: continue
    title=one(attrs,'block/title')
    if not isinstance(title,str): continue
    page_id=one(attrs,'block/page'); parent=one(attrs,'block/parent')
    if isinstance(page_id,int) and page_id in pages:
        block_info[eid]={'id':eid,'title':title,'page_id':page_id,'parent':parent if isinstance(parent,int) else page_id,
                         'uuid':one(attrs,'block/uuid',''),'order':str(one(attrs,'block/order','')),
                         'tags':attrs.get('block/tags',[]),'refs':attrs.get('block/refs',[])}
        children[block_info[eid]['parent']].append(eid)
for par in children: children[par].sort(key=lambda eid:(block_info[eid]['order'],eid))
block_by_uuid={b['uuid']:b for b in block_info.values() if b['uuid']}
page_blocks=collections.defaultdict(set)
for bid,b in block_info.items(): page_blocks[b['page_id']].add(bid)

# Incoming saved graph links. Keep the referring block ID so references can jump to it.
incoming_linked=collections.defaultdict(dict)
for source_id,attrs in entities.items():
    refs={r for r in attrs.get('block/refs',[]) if isinstance(r,int)}
    if not refs: continue
    if source_id in pages:
        source={'kind':'page','id':source_id,'page_id':source_id,'title':pages[source_id]['title'],'uuid':pages[source_id]['uuid'],'text':pages[source_id]['title']}
    elif source_id in block_info:
        b=block_info[source_id]
        source={'kind':'block','id':source_id,'page_id':b['page_id'],'title':b['title'],'uuid':b['uuid'],'text':b['title']}
    else: continue
    for target_page_id in pages:
        targets={target_page_id}|page_blocks.get(target_page_id,set())
        if refs.intersection(targets) and source['page_id'] != target_page_id:
            incoming_linked[target_page_id][source_id]=source

# Candidate unlinked page-title matches. They are clearly candidates, not verified links.
short_acronyms={'RSP','LUP','NEP','NPD','NES','NPS'}
stop_titles={'root tag','tag','property','page','template','favorites','heading','quote','state','file type','external url','published url','table view pinned columns','annotation image'}
target_patterns=[]
for target in pages.values():
    title=clean_text(target['title'])
    if title.casefold() in stop_titles or (len(title)<4 and title.upper() not in short_acronyms): continue
    target_patterns.append((target,re.compile(r'(?<![\w])'+re.escape(title)+r'(?![\w])',re.I)))
unlinked_refs=collections.defaultdict(list)
for bid,b in block_info.items():
    source_text=b['title']; source_refs={r for r in entities[bid].get('block/refs',[]) if isinstance(r,int)}
    if not source_text: continue
    for target,pattern in target_patterns:
        if b['page_id']==target['id'] or source_refs.intersection({target['id']}|page_blocks.get(target['id'],set())): continue
        match=pattern.search(source_text)
        if match:
            start,end=match.span(); excerpt=source_text[max(0,start-100):min(len(source_text),end+140)]
            if start>100: excerpt='…'+excerpt
            if end+140<len(source_text): excerpt+='…'
            unlinked_refs[target['id']].append({'kind':'block','id':bid,'page_id':b['page_id'],'title':source_text,'uuid':b['uuid'],'text':excerpt})

def tag_titles(tag_ids):
    # Resolve tag IDs to human-readable entity titles rather than exposing database IDs.
    return [pages[t]['title'] if t in pages else entity_title_by_id.get(t,str(t)) for t in tag_ids]
def page_has_tag(page_id,*wanted):
    w={x.casefold() for x in wanted}
    return any(str(t).casefold() in w for t in tag_titles(pages[page_id]['tags']))
def statutory_sort_key(title):
    t=clean_text(title)
    m=re.match(r'^\s*(?:§\s*|section\s+|s\.?\s*)(\d+)\b',t,re.I)
    if m: return (0,int(m.group(1)),t.casefold())
    m=re.match(r'^\s*schedule\s+(\d+)\b',t,re.I)
    if m: return (1,int(m.group(1)),t.casefold())
    return (2,10**9,t.casefold())

def resolve_uuid(uid):
    if uid in page_by_uuid: return f"{page_by_uuid[uid]['slug']}.html"
    if uid in block_by_uuid:
        b=block_by_uuid[uid]; return f"{pages[b['page_id']]['slug']}.html#block-{b['uuid'] or 'id-'+str(b['id'])}"
    return None

def render_links(s,prefix=''):
    links=[]
    def hold(label,uid):
        target=resolve_uuid(uid)
        if not target: return html.escape(label)
        token=f'LOGSEQLINKTOKEN{len(links)}END'
        links.append((token,f'<a href="{html.escape(prefix+target,quote=True)}">{html.escape(label)}</a>'))
        return token
    def labeled(m): return hold(m.group(1),m.group(2))
    s=re.sub(r'\[((?:[^\[\]]|\[[^\]]*\])*)\]\(\[\[([0-9a-fA-F-]{36})\]\]\)',labeled,s)
    def bare(m):
        uid=m.group(1)
        if uid in page_by_uuid: label=page_by_uuid[uid]['title']
        elif uid in block_by_uuid: label=block_by_uuid[uid]['title']
        elif uid in entity_by_uuid: label=one(entity_by_uuid[uid][1],'block/title',uid)
        else: label=uid
        return hold(label,uid)
    s=re.sub(r'\[\[([0-9a-fA-F-]{36})\]\]',bare,s)
    s=html.escape(s)
    for token,anchor in links: s=s.replace(token,anchor)
    s=re.sub(r'`([^`]+)`',r'<code>\1</code>',s)
    s=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',s)
    s=re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)',r'<em>\1</em>',s)
    return s

def reference_href(ref,from_root=False):
    prefix='pages/' if from_root else ''
    if ref['kind']=='page': return prefix+pages[ref['page_id']]['slug']+'.html'
    b=block_info.get(ref['id'])
    if not b: return prefix+pages[ref['page_id']]['slug']+'.html'
    return prefix+pages[b['page_id']]['slug']+'.html#block-'+(b['uuid'] or f'id-{b["id"]}')

def merge_references(page_id):
    merged={}
    for r in incoming_linked.get(page_id,{}).values():
        key=(r.get('page_id'),r.get('id')); item=dict(r); item['linked']=True; item['text']=item.get('text') or item.get('title',''); merged[key]=item
    for r in unlinked_refs.get(page_id,[]):
        key=(r.get('page_id'),r.get('id'))
        if key not in merged:
            item=dict(r); item['linked']=False; merged[key]=item
    return sorted(merged.values(),key=lambda r:(statutory_sort_key(pages[r['page_id']]['title']),clean_text(r.get('text',r.get('title',''))).casefold()))

def reference_item_html(ref,from_root=False):
    source_title=pages[ref['page_id']]['title']; href=reference_href(ref,from_root); excerpt=clean_text(ref.get('text',ref.get('title','')))
    bid=ref.get('id'); ancestors=[]; seen_ancestors=set()
    while bid in block_info and bid not in seen_ancestors:
        seen_ancestors.add(bid); block=block_info[bid]; ancestors.append(clean_text(block['title']))
        parent=block.get('parent'); bid=parent if parent in block_info else None
    context=' / '.join(reversed(ancestors[:-1])) if len(ancestors)>1 else ''
    context=context[:360].rstrip() + ('…' if len(context)>360 else '')
    excerpt=excerpt[:360].rstrip() + ('…' if len(excerpt)>360 else '')
    searchable=source_title+' '+context+' '+excerpt
    context_html=f'<div class="reference-context">{render_links(context, "pages/" if from_root else "")}</div>' if context else ''
    return (f'<li class="reference-item" data-filter-text="{html.escape(searchable.casefold(),quote=True)}" data-start-text="{html.escape(excerpt.casefold(),quote=True)}">'
            f'<a href="{html.escape(href,quote=True)}">{html.escape(source_title)}</a>{context_html}'
            f'<p class="reference-extract">{render_links(excerpt, "pages/" if from_root else "")}</p></li>')

def reference_box(title,items,from_root=False,filterable=False):
    rows=''.join(reference_item_html(r,from_root) for r in items)
    filt='<input class="reference-filter" type="search" placeholder="Filter these references…" aria-label="Filter these references">' if filterable else ''
    empty='<p class="ref-empty">No references found.</p>' if not items else ''
    mode='starts' if title.startswith('§3') else 'contains'
    return f'<section class="reference-box" data-filter-mode="{mode}"><h3>{html.escape(title)} <span class="ref-count">{len(items)}</span></h3>{filt}<ul class="reference-list">{rows}</ul>{empty}</section>'

def is_concept_or_actor(p):
    return any(str(x).casefold() in {'concept','actor','concepts'} for x in tag_titles(p['tags']))
def reference_section(page_id,from_root=False,grouped=False):
    items=merge_references(page_id)
    if not grouped:
        return '<section class="reference-section"><h2 class="section-heading">References and connections</h2>'+reference_box('References',items,from_root,True)+'</section>'
    interpretation_norms={'3 interpretation','section 3 interpretation','npd interpretation'}
    def is_interpretation(r):
        n=re.sub(r'[^a-z0-9]+',' ',pages[r['page_id']]['title'].casefold()).strip()
        return n in interpretation_norms
    interpretation=[r for r in items if is_interpretation(r)]
    instruments={'RSP':[],'LUP':[],'NEP':[]}; others=[]
    for r in items:
        if is_interpretation(r): continue
        labels={str(x).casefold() for x in tag_titles(pages[r['page_id']]['tags'])}; placed=False
        for label in ('RSP','LUP','NEP'):
            if label.casefold() in labels: instruments[label].append(r); placed=True
        if not placed: others.append(r)
    top='<h2 class="section-heading">Interpretation</h2>'+reference_box('§3 – Interpretation / NPD Interpretation',interpretation,from_root,True)
    related='<h2 class="section-heading">Related instruments</h2><div class="instrument-reference-grid">'+''.join(reference_box(k,instruments[k],from_root,True) for k in ('RSP','LUP','NEP'))+'</div>'
    other='<h2 class="section-heading">Other references</h2>'+reference_box('All other references',others,from_root,True)
    return '<section class="reference-section">'+top+related+other+'</section>'

def render_block(eid,seen,prefix=''):
    if eid in seen or eid not in block_info: return ''
    seen.add(eid); b=block_info[eid]; uid=b['uuid'] or f'id-{eid}'
    title_html=render_links(b['title'],prefix); labels=tag_titles(b['tags'])
    tag_html=''.join(f'<span class="tag">{html.escape(str(t))}</span>' for t in labels if t)
    child_ids=children.get(eid,[]); kids=''.join(render_block(k,seen,prefix) for k in child_ids)
    toggle='<button class="block-toggle" type="button" aria-expanded="true" aria-label="Collapse block" title="Collapse/expand block">−</button>' if child_ids else ''
    child_html=f'<ul class="block-children">{kids}</ul>' if child_ids else ''
    tags_html=f'<div class="tags">{tag_html}</div>' if tag_html else ''
    return f'<li class="block-item" id="block-{html.escape(uid)}">{toggle}<div class="block-text">{title_html}</div>{tags_html}{child_html}</li>'

if out.exists(): shutil.rmtree(out)
(out/'pages').mkdir(parents=True, exist_ok=True); (out/'assets').mkdir(parents=True, exist_ok=True)
# Copy brand assets on every build so the deployment workflow cannot omit or erase them.
for asset_name in ('favicon.ico', 'favicon-16.png', 'favicon-32.png', 'apple-touch-icon.png', 'favicon-512.png'):
    source_asset = brand_assets / asset_name
    if source_asset.is_file():
        shutil.copy2(source_asset, out / asset_name)
    else:
        raise SystemExit(f'Missing required favicon asset: {source_asset}')
shutil.copy2(brand_assets / 'bosch-funnel-icon.png', out / 'assets' / 'bosch-funnel-icon.png')

def favicon_links(prefix=''):
    return (f'<link rel="icon" type="image/png" sizes="32x32" href="{prefix}favicon-32.png">'
            f'<link rel="icon" type="image/png" sizes="16x16" href="{prefix}favicon-16.png">'
            f'<link rel="shortcut icon" href="{prefix}favicon.ico">'
            f'<link rel="apple-touch-icon" sizes="180x180" href="{prefix}apple-touch-icon.png">')
css='''*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:20px}body{margin:0;background:#f5f1e7;color:#302f2a;font:16px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:#9a5b36;text-decoration:none;overflow-wrap:anywhere}a:hover{text-decoration:none;color:#6f3d25}.wrap{max-width:1500px;margin:auto;padding:24px 22px}.top{background:#173f37;color:white}.top a{color:white}.brand{font-weight:750;letter-spacing:.01em;font-size:1.1rem}.hero{padding:10px 0 12px}.hero h1{font-size:clamp(1.7rem,4vw,2.6rem);margin:.25rem 0 .5rem}.hero p{margin:.35rem 0}.hero h1{font-size:clamp(1.7rem,4vw,2.6rem);line-height:1.08;margin:.25rem 0 .5rem;max-width:780px}.hero p{max-width:720px;color:#e0ebe6}.search{display:flex;gap:8px;margin:18px 0 8px;max-width:780px}.search input,.sidebar-search input{flex:1;min-width:0;padding:11px 12px;border:1px solid #d7d0bf;border-radius:7px;font:inherit}.search button,.button{padding:9px 12px;border:1px solid #d7d0bf;border-radius:7px;background:#e8e0cc;color:#403f36;font-weight:650;cursor:pointer}.layout{display:grid;grid-template-columns:260px minmax(0,1fr);gap:24px;align-items:start}.panel,.content-card{background:#fffdf8;border:1px solid #ded6c4;border-radius:9px;padding:18px;min-width:0}.panel h2,.content-card h2{margin-top:0}.sidebar{position:sticky;top:12px;max-height:calc(100vh - 24px);overflow:auto}.navlist{padding:0;list-style:none}.navlist li{margin:.55rem 0}.muted{color:#68746e}.small{font-size:.88rem}.result{background:white;border:1px solid #e1e5e1;border-radius:10px;padding:14px}.pill{display:inline-block;background:#eef2ef;color:#47544d;border-radius:99px;padding:2px 8px;font-size:.78rem;margin:2px 4px 2px 0}.tag{display:inline-block;background:transparent;border:1px solid #d7c9a6;color:#75694f;border-radius:3px;padding:1px 6px;font-size:.75rem;margin:2px 4px 2px 0;white-space:normal}.crumb{font-size:.88rem;color:#65716b;margin-bottom:12px}.page-title{font-size:clamp(1.8rem,4vw,2.5rem);line-height:1.15;margin:.2rem 0 1rem}.page-tree{padding-left:1.35rem}.page-tree>li{padding:.25rem 0}.page-tree ul{padding-left:1.4rem;margin:.35rem 0}.block-item{position:relative;padding:.18rem 0}.block-text{white-space:pre-wrap;overflow-wrap:anywhere}.block-toggle{position:absolute;left:-1.55rem;top:.18rem;width:1.2rem;height:1.35rem;display:inline-flex;align-items:center;justify-content:center;padding:0;border:1px solid #d6ddd8;border-radius:4px;background:#f5f7f5;color:#31564a;font-size:.9rem;line-height:1;cursor:pointer;z-index:1}.block-toggle:hover{background:#e5eee8}.block-children{margin:.3rem 0 .25rem;padding-left:1.4rem}.tags{margin-top:5px}.empty{padding:18px;border:1px dashed #cbd4cf;border-radius:10px;color:#65716b}.footer{margin-top:42px;padding-top:18px;border-top:1px solid #dce2dd;color:#65716b;font-size:.85rem}.reference-section{margin-top:22px;min-width:0}.reference-box{background:#fffdf8;border:1px solid #ded6c4;border-radius:8px;padding:14px;min-width:0;width:100%;overflow-wrap:anywhere}.reference-box h3{margin:0 0 10px;font-size:1rem}.ref-count{display:inline-block;background:#eee6d2;border-radius:3px;padding:1px 7px;font-size:.8rem;margin-left:6px}.reference-list{list-style:none;padding:0;margin:0;min-width:0}.reference-item{border-top:1px solid #eee8dc;padding:12px 0;min-width:0;overflow-wrap:anywhere}.reference-item:first-child{border-top:0}.reference-context{margin:5px 0 2px;color:#9a968b;font-size:.78rem;line-height:1.4;overflow-wrap:anywhere;word-break:normal}.reference-item .reference-extract{margin:2px 0 0;color:#59665f;font-size:.92rem;overflow-wrap:anywhere;word-break:normal}.ref-empty{color:#65716b;font-size:.92rem;margin:.4rem 0}.section-heading{margin:25px 0 10px}.home-content{margin-top:18px}.reference-filter{width:100%;padding:9px 10px;margin:0 0 10px;border:1px solid #d7d0bf;border-radius:7px;font:inherit}.instrument-reference-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:14px;align-items:start;width:100%;min-width:0}.instrument-reference-grid>*{min-width:0;width:100%}.search-highlight{background:#ffef70;color:#202522;border-radius:2px;padding:0 .03em}.search-group{margin:18px 0;min-width:0}.search-group h2{font-size:1.15rem;margin:.2rem 0 .7rem}.search-group-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;min-width:0}.search-group-grid>.search-group .search-group-grid{grid-template-columns:minmax(0,1fr);gap:10px}.search-group-grid>.search-group .search-ref{width:100%;min-width:0}.search-ref{background:#fffdf8;border:1px solid #ded6c4;border-radius:8px;padding:12px;min-width:0;overflow-wrap:anywhere}.search-ref h3{font-size:.98rem;margin:0 0 5px}.search-ref p{font-size:.91rem;margin:.3rem 0;color:#59665f;overflow-wrap:anywhere}.search-other-filter{width:100%;padding:10px;border:1px solid #cbd4cf;border-radius:7px;font:inherit;margin:0 0 10px}.sidebar-search{display:flex;gap:6px;margin-bottom:18px}.sidebar-search button{border:1px solid #d7d0bf;background:#e8e0cc;border-radius:7px;padding:8px;cursor:pointer}.side-section{border-top:1px solid #e8e0d0;padding-top:12px;margin-top:14px}.side-section h3{font-size:.92rem;margin:0 0 8px}.side-tree{list-style:none;padding-left:12px;margin:0}.side-tree li{margin:4px 0}.side-tree details>summary{cursor:pointer;color:#47594e;font-weight:650}.side-tree a{font-size:.9rem}.recent-list{padding-left:18px;margin:0}.recent-list li{margin:5px 0;font-size:.9rem}.page-jump{position:fixed;right:16px;top:50%;transform:translateY(-50%);z-index:50;display:flex;flex-direction:column;gap:7px}.page-jump a{display:flex;align-items:center;justify-content:center;width:42px;height:42px;border:1px solid #d7c9a6;border-radius:8px;background:#fffdf8;color:#31564a;text-decoration:none;box-shadow:0 2px 8px #00000012;font-size:1.1rem}.page-jump a:hover{background:#e8e0cc}@media(max-width:900px){.layout{grid-template-columns:220px minmax(0,1fr);gap:14px}.wrap{padding:18px 14px}.instrument-reference-grid,.search-group-grid{grid-template-columns:1fr}}@media(max-width:680px){.layout{grid-template-columns:1fr}.sidebar{position:relative;top:auto;max-height:none}.search{flex-direction:column}.search button{width:100%}.page-jump{right:8px}.page-jump a{width:36px;height:36px}}'''
(out/'assets/style.css').write_text(css,encoding='utf-8')

# Search index includes full page text and graph tags for grouped search results.
search_records=[]
for p in pages.values():
    block_ids=[]; seen=set()
    def walk(pid):
        for bid in children.get(pid,[]):
            if bid in seen: continue
            seen.add(bid); block_ids.append(bid); walk(bid)
    walk(p['id']); body=' '.join(block_info[bid]['title'] for bid in block_ids)
    search_records.append({'title':p['title'],'slug':p['slug'],'name':p['name'],'tags':tag_titles(p['tags']),'text':clean_text(body)[:50000]})
(out/'assets'/'search-index.json').write_text(json.dumps(search_records,ensure_ascii=False),encoding='utf-8')

page_script='''<script>
function bindRecentPages(){const key='pa-recent-pages-v5',list=document.getElementById('recent-pages');if(!list)return;let items=[];try{items=JSON.parse(localStorage.getItem(key)||'[]')}catch(e){}const current=document.querySelector('h1.page-title');if(current){const title=current.textContent.trim(),href=location.pathname+location.search+location.hash;items=[{title,href},...items.filter(x=>x.href!==href)].slice(0,8);try{localStorage.setItem(key,JSON.stringify(items))}catch(e){}}list.innerHTML=items.length?items.map(x=>'<li><a href="'+escSidebar(x.href)+'">'+escSidebar(x.title)+'</a></li>').join(''):'<li class="muted small">Pages you visit will appear here.</li>'}function escSidebar(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function bindBlockToggles(){document.querySelectorAll('.block-toggle').forEach(btn=>btn.addEventListener('click',()=>{const li=btn.closest('.block-item');const kids=li.querySelector(':scope > .block-children');if(!kids)return;const open=btn.getAttribute('aria-expanded')==='true';kids.hidden=open;btn.setAttribute('aria-expanded',String(!open));btn.textContent=open?'+':'−';btn.setAttribute('aria-label',open?'Expand block':'Collapse block')}));const ex=document.getElementById('expand-all'),co=document.getElementById('collapse-all');if(ex)ex.addEventListener('click',()=>document.querySelectorAll('.block-item > .block-children').forEach(ul=>{ul.hidden=false;const b=ul.parentElement.querySelector(':scope > .block-toggle');if(b){b.textContent='−';b.setAttribute('aria-expanded','true');b.setAttribute('aria-label','Collapse block')}}));if(co)co.addEventListener('click',()=>document.querySelectorAll('.block-item > .block-children').forEach(ul=>{ul.hidden=true;const b=ul.parentElement.querySelector(':scope > .block-toggle');if(b){b.textContent='+';b.setAttribute('aria-expanded','false');b.setAttribute('aria-label','Expand block')}}))}
function bindReferenceFilters(){document.querySelectorAll('.reference-filter').forEach(input=>input.addEventListener('input',()=>{const box=input.closest('.reference-box'),q=input.value.trim().toLowerCase(),starts=box.dataset.filterMode==='starts';box.querySelectorAll('.reference-item').forEach(item=>{const hay=starts?(item.dataset.startText||''):(item.dataset.filterText||'');item.hidden=starts?!hay.startsWith(q):!hay.includes(q)})}))}
function highlightQuery(){const q=new URLSearchParams(location.search).get('q');if(!q)return;const esc=q.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&');if(!esc)return;const re=new RegExp(esc,'gi'),root=document.querySelector('main')||document.body,walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentElement&&!['SCRIPT','STYLE','MARK','INPUT','TEXTAREA'].includes(n.parentElement.tagName)&&n.nodeValue.toLowerCase().includes(q.toLowerCase())?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT}),nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);nodes.forEach(node=>{const frag=document.createDocumentFragment();let last=0;node.nodeValue.replace(re,(m,off)=>{frag.appendChild(document.createTextNode(node.nodeValue.slice(last,off)));const mark=document.createElement('mark');mark.className='search-highlight';mark.textContent=m;frag.appendChild(mark);last=off+m.length;return m});frag.appendChild(document.createTextNode(node.nodeValue.slice(last)));node.parentNode.replaceChild(frag,node)})}
bindBlockToggles();bindReferenceFilters();bindRecentPages();highlightQuery();document.querySelectorAll('.side-provision-toggle').forEach(b=>b.addEventListener('click',()=>{const d=b.nextElementSibling;if(d)d.open=!d.open}));
</script>'''

# Shared left navigation: search, recent pages, graph exploration, and collapsible provision hierarchy.
provision_pages=[p for p in pages.values() if page_has_tag(p['id'],'provision')]
part_pages=[p for p in pages.values() if re.match(r'^(part|subpart)\s+[0-9ivxlcdm]+',p['title'].strip(),re.I)]
def nav_href(p,from_root=False): return ('../' if from_root else '')+'pages/'+p['slug']+'.html'
def sidebar_html(from_root=False):
    prefix='../' if from_root else ''
    provision_items=sorted(provision_pages,key=lambda p:statutory_sort_key(p['title']))
    # Group by Part/Subpart headings when those pages exist; otherwise retain one searchable provisions list.
    groups=collections.OrderedDict()
    for p in provision_items:
        m=re.match(r'^(Part\s+[0-9ivxlcdm]+[^:–—-]*|Subpart\s+[0-9ivxlcdm]+[^:–—-]*)',p['title'].strip(),re.I)
        key=m.group(1) if m else 'All provisions'
        groups.setdefault(key,[]).append(p)
    tree=[]
    for label,items in groups.items():
        tree.append('<li><details><summary>'+html.escape(label)+' ('+str(len(items))+')</summary><ul class=\"side-tree\">'+''.join('<li><a href=\"'+nav_href(p,from_root)+'\">'+html.escape(p['title'])+'</a></li>' for p in items)+'</ul></details></li>')
    return f'''<aside class=\"panel sidebar\"><form class=\"sidebar-search\" action=\"{prefix}index.html\" method=\"get\"><input type=\"search\" name=\"q\" placeholder=\"Search the graph…\" aria-label=\"Search the graph\"><button type=\"submit\">Go</button></form><section class=\"side-section\"><h3>Recently visited</h3><ol class=\"recent-list\" id=\"recent-pages\"></ol></section><section class=\"side-section\"><h3>Explore the graph</h3><ul class=\"navlist\"><li><a href=\"{prefix}provisions.html\">Planning Act provisions</a></li><li><a href=\"{prefix}concepts-expressions.html\">Concepts</a></li><li><a href=\"{prefix}planning-instruments.html\">Key Instruments</a></li><li><a href=\"{prefix}actors.html\">Actors</a></li></ul></section><section class=\"side-section\"><h3>Planning Act provisions</h3><ul class=\"side-tree\">{''.join(tree)}</ul></section></aside>'''

# Render individual pages. Concept and actor pages use special reference grouping.
for p in pages.values():
    seen=set(); tree=''.join(render_block(bid,seen) for bid in children.get(p['id'],[]))
    tags=''.join(f'<span class="tag">{html.escape(str(t))}</span>' for t in tag_titles(p['tags']) if t)
    refs_html=reference_section(p['id'],grouped=is_concept_or_actor(p))
    controls='<button type="button" class="button" id="expand-all">Expand all blocks</button> <button type="button" class="button" id="collapse-all">Collapse all blocks</button>'
    body=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(p['title'])} · Planning Act Knowledge Base</title>{favicon_links('../')}<link rel="stylesheet" href="../assets/style.css"></head><body><header class="top"><div class="wrap"><a class="brand" href="../index.html">Planning Act Knowledge Base</a></div></header><main class="wrap"><div class="layout">{sidebar_html(True)}<section class="main-column"><div class="crumb"><a href="../index.html">Home</a> / Knowledge graph</div><h1 class="page-title">{html.escape(p['title'])}</h1><div class="tags">{tags}</div><section class="content-card"><div class="block-controls">{controls}</div><ul class="page-tree">{tree or '<li class="muted">No child blocks were found for this page.</li>'}</ul></section>{refs_html}<div class="footer">Generated from the supplied Logseq EDN export. Confirm statutory wording and context against official legislation.</div></section></div><nav class="page-jump" aria-label="Page navigation"><a href="#" aria-label="Go to top" title="Go to top">↑</a><a href="#page-bottom" aria-label="Go to bottom" title="Go to bottom">↓</a></nav><span id="page-top"></span><span id="page-bottom"></span></main>{page_script}</body></html>'''
    (out/'pages'/f"{p['slug']}.html").write_text(body,encoding='utf-8')

# Browse pages from existing graph tags.
def has_tag(p,*labels): return any(str(t).casefold() in {x.casefold() for x in labels} for t in tag_titles(p['tags']))
browse_categories=[
 {'slug':'provisions','title':'Provisions','description':'Browse provision pages and statutory material already tagged as provisions.','items':[p for p in pages.values() if has_tag(p,'provision')]},
 {'slug':'concepts-expressions','title':'Concepts','description':'Explore concepts and follow references to provisions.','items':[p for p in pages.values() if has_tag(p,'concept')]},
 {'slug':'planning-instruments','title':'Key Instruments','description':'Navigate pages tagged RSP, LUP and NEP. These labels reflect existing graph tags.','items':[p for p in pages.values() if has_tag(p,'RSP','LUP','NEP','instrument')]},
 {'slug':'actors','title':'Actors','description':'Find actor pages and follow references to their statutory roles.','items':[p for p in pages.values() if has_tag(p,'Actor')]},
]
for cat in browse_categories:
    if cat['slug']=='planning-instruments':
        parts=[]
        for label in ('RSP','LUP','NEP'):
            items=sorted([p for p in cat['items'] if has_tag(p,label)],key=lambda p:statutory_sort_key(p['title']))
            parts.append(f'<h2>{label}</h2><ul class="navlist">'+''.join(f'<li><a href="pages/{p["slug"]}.html">{html.escape(p["title"])}</a></li>' for p in items)+'</ul>')
        list_html=''.join(parts)
    else:
        list_html='<ul class="navlist">'+''.join(f'<li><a href="pages/{p["slug"]}.html">{html.escape(p["title"])}</a></li>' for p in sorted(cat['items'],key=lambda p:statutory_sort_key(p['title'])))+'</ul>'
    page_html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(cat['title'])} · Planning Act Knowledge Base</title>{favicon_links()}<link rel="stylesheet" href="assets/style.css"></head><body><header class="top"><div class="wrap"><a class="brand" href="index.html">Planning Act Knowledge Base</a></div></header><main class="wrap"><div class="layout">{sidebar_html(False)}<section class="main-column"><div class="crumb"><a href="index.html">Home</a> / Browse</div><h1 class="page-title">{html.escape(cat['title'])}</h1><p>{html.escape(cat['description'])}</p><section class="content-card"><p class="muted small">{len(cat['items'])} matching pages</p>{list_html}</section><div class="footer"><a href="index.html">Return to home</a></div></section></div><nav class="page-jump" aria-label="Page navigation"><a href="#" aria-label="Go to top">↑</a><a href="#page-bottom" aria-label="Go to bottom">↓</a></nav><span id="page-top"></span><span id="page-bottom"></span>{page_script}</main></body></html>'''
    (out/f"{cat['slug']}.html").write_text(page_html,encoding='utf-8')

# Homepage uses the existing Planning Act home page content, without the all-pages list.
def is_home_page(p):
    n=re.sub(r'[^a-z0-9]+',' ',p['title'].casefold()).strip()
    return 'planning act' in n and 'home' in n
home_page=next((p for p in pages.values() if is_home_page(p)),None)
home_tree=''; home_tags=''; home_refs=''
if home_page:
    seen=set(); home_tree=''.join(render_block(bid,seen,'pages/') for bid in children.get(home_page['id'],[]))
    home_tags=''.join(f'<span class="tag">{html.escape(str(t))}</span>' for t in tag_titles(home_page['tags']))
    home_refs=reference_section(home_page['id'],True,is_concept_or_actor(home_page))
root_title=home_page['title'] if home_page else 'Planning Act Knowledge Base'
index_script='''<script>
let records=[];const form=document.getElementById('search-form'),input=document.getElementById('q'),results=document.getElementById('results'),status=document.getElementById('search-status');fetch('assets/search-index.json').then(r=>r.json()).then(d=>{records=d;status.textContent=`Ready to search ${records.length.toLocaleString()} pages.`;const initial=new URLSearchParams(location.search).get('q');if(initial){input.value=initial;form.requestSubmit()}}).catch(()=>{status.textContent='Could not load the search index. Please rebuild the site.'});
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function termsFor(q){return q.toLowerCase().trim().split(/\s+/).filter(Boolean)}
function hi(s,q){const terms=termsFor(q).sort((a,b)=>b.length-a.length),lower=s.toLowerCase();let out='',i=0;while(i<s.length){const t=terms.find(t=>lower.startsWith(t,i));if(t){out+='<mark class="search-highlight">'+esc(s.slice(i,i+t.length))+'</mark>';i+=t.length}else{out+=esc(s[i]);i++}}return out}
function isInterp(p){const n=p.title.toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();return n==='npd interpretation'||n==='3 interpretation'||n==='section 3 interpretation'}
function renderGroup(title,items,q,filter=false){let h='<section class="search-group"><h2>'+esc(title)+' <span class="ref-count">'+items.length+'</span></h2>';if(filter)h+='<input class="search-other-filter" type="search" placeholder="Filter other references…" aria-label="Filter other references">';if(!items.length)h+='<p class="muted">No matching references.</p>';else{h+='<div class="search-group-grid">';for(const p of items){const lower=(p.text||'').toLowerCase(),terms=termsFor(q),positions=terms.map(t=>lower.indexOf(t)).filter(i=>i>=0),idx=positions.length?Math.min(...positions):-1;let ex=idx>=0?p.text.slice(Math.max(0,idx-100),Math.min(p.text.length,idx+Math.max(...terms.map(t=>t.length))+220)):p.text.slice(0,220);h+='<article class="search-ref" data-filter-text="'+esc((p.title+' '+ex).toLowerCase())+'"><h3><a href="pages/'+esc(p.slug)+'.html?q='+encodeURIComponent(q)+'">'+hi(p.title,q)+'</a></h3><p>'+p.tags.slice(0,4).map(t=>'<span class="tag">'+hi(t,q)+'</span>').join(' ')+'</p><p>'+hi(ex,q)+'</p></article>'}h+='</div>'}return h+'</section>'}
form.addEventListener('submit',e=>{e.preventDefault();const q=input.value.trim(),terms=termsFor(q);results.innerHTML='';if(!q){status.textContent=`Search ${records.length.toLocaleString()} pages.`;return}const hits=records.map(p=>{const title=(p.title||'').toLowerCase(),tags=(p.tags||[]).join(' ').toLowerCase(),hay=(title+' '+(p.name||'')+' '+tags+' '+(p.text||'')).toLowerCase();const score=terms.reduce((n,t)=>n+(title.includes(t)?4:0)+(tags.includes(t)?2:0+0)+(hay.includes(t)?1:0),0);return {...p,score,hay}}).filter(p=>terms.every(t=>p.hay.includes(t))).sort((a,b)=>b.score-a.score||a.title.localeCompare(b.title));status.textContent=`${hits.length} matching pages. All search terms must match; matching terms are highlighted.`;if(!hits.length){results.innerHTML='<div class="empty">No matches found for all terms. Try fewer words or a different spelling.</div>';return}const interp=hits.filter(isInterp),groups={RSP:[],LUP:[],NEP:[]},other=[];for(const p of hits){if(isInterp(p))continue;let placed=false;const pageText=(p.text||'').toLowerCase(),tagSet=new Set((p.tags||[]).map(t=>t.toLowerCase().trim()));const aliases={RSP:['regional spatial plan','regional spatial plans','rsp'],LUP:['land use plan','land use plans','lup'],NEP:['natural environment plan','natural environment plans','nep']};for(const k of Object.keys(groups)){const byTag=tagSet.has(k.toLowerCase())||(p.tags||[]).some(t=>t.toLowerCase().includes(k.toLowerCase()));const normalizedText=' '+pageText.replace(/[^a-z0-9]+/g,' ')+' ';const byText=aliases[k].some(term=>normalizedText.includes(' '+term+' '));if(byTag||byText){groups[k].push(p);placed=true}}if(!placed)other.push(p)}const firstTerm=terms[0];const interpFiltered=interp.filter(p=>(p.text||'').toLowerCase().startsWith(firstTerm));results.innerHTML=renderGroup('Interpretation',interpFiltered,q)+'<section class="search-group"><h2>Related instruments</h2><div class="search-group-grid">'+['RSP','LUP','NEP'].map(k=>renderGroup(k,groups[k],q)).join('')+'</div></section>'+renderGroup('Other references',other,q,true);results.querySelectorAll('.search-other-filter').forEach(el=>el.addEventListener('input',()=>{const q2=el.value.toLowerCase();el.parentElement.querySelectorAll('.search-ref').forEach(card=>card.hidden=!card.dataset.filterText.includes(q2))}))});
</script>'''
index_html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(root_title)} · Planning Act Knowledge Base</title>{favicon_links()}<link rel="stylesheet" href="assets/style.css"></head><body><header class="top"><div class="wrap"><div class="brand">Planning Act Knowledge Base</div><section class="hero"><h1>{html.escape(root_title)}</h1><p>Explore provisions, concepts, planning instruments and actors across the legislation.</p><form class="search" id="search-form"><input id="q" type="search" placeholder="Search provisions, concepts, expressions or actors…" aria-label="Search"><button type="submit">Search</button></form><p class="small">Search results are grouped by interpretation, RSP, LUP, NEP and other references.</p></section></div></header><main class="wrap"><div class="layout">{sidebar_html(False)}<section class="main-column"><section class="content-card" style="display:flex;align-items:center;gap:18px;margin-bottom:18px;flex-wrap:wrap"><a href="https://eclecticlight.co/2016/08/14/funnels-jewish-hats-and-wizardry-the-influence-of-boschs-visual-inventions/" target="_blank" rel="noopener noreferrer" aria-label="Read the article about Bosch’s visual inventions" style="display:block;flex:0 0 96px"><img src="assets/bosch-funnel-icon.png" alt="Bosch-inspired funnel-shaped figure" style="display:block;width:96px;height:96px;object-fit:contain"></a><div style="flex:1;min-width:220px"><h2 style="margin:0 0 5px">A visual note: Bosch’s funnel figure</h2><p style="margin:0">The funnel-shaped figure is a small visual motif for this knowledge garden. <a href="https://eclecticlight.co/2016/08/14/funnels-jewish-hats-and-wizardry-the-influence-of-boschs-visual-inventions/" target="_blank" rel="noopener noreferrer">Read the article on Bosch’s visual inventions</a>.</p></div></section><div id="search-status" class="muted">Loading search index…</div><div id="results"></div><section class="content-card home-content"><h2>Planning Act home page</h2><div class="tags">{home_tags}</div><ul class="page-tree">{home_tree or '<li class="muted">No blocks were found on the configured home page.</li>'}</ul></section>{home_refs}</section></div><nav class="page-jump" aria-label="Page navigation"><a href="#" aria-label="Go to top" title="Go to top">↑</a><a href="#page-bottom" aria-label="Go to bottom" title="Go to bottom">↓</a></nav><span id="page-top"></span><span id="page-bottom"></span><div class="footer">Generated from your Logseq EDN export. Verify statutory wording against official legislation.</div></main>{index_script}{page_script}</body></html>'''
(out/'index.html').write_text(index_html,encoding='utf-8')

manifest={'source_file':src.name,'datoms_parsed':count,'entities':len(entities),'pages':len(pages),'blocks_with_page':len(block_info),'pages_without_children':sum(not children.get(pid) for pid in pages),'generated_files':len(pages)+len(browse_categories)+3,'home_page':home_page['title'] if home_page else None,'pages_with_linked_references':sum(bool(incoming_linked.get(p['id'])) for p in pages.values()),'pages_with_unlinked_references':sum(bool(unlinked_refs.get(p['id'])) for p in pages.values()),'linked_reference_edges':sum(len(v) for v in incoming_linked.values()),'unlinked_reference_matches':sum(len(v) for v in unlinked_refs.values()),'browse_category_counts':{c['title']:len(c['items']) for c in browse_categories},'prototype_notes':['Page and block titles are extracted from :block/title.','Block ordering uses the exported :block/order value.','UUID links resolve to human-readable page or block titles where available.','Saved and candidate references are merged and sorted numerically by statutory provision, then schedule.','Concept and actor pages group references by interpretation, RSP, LUP, NEP and other references.','Version 4 adds sticky graph navigation, recent pages, provision groups, page-jump controls, improved reference snippets and tag styling.','Unlinked references are candidate page-title matches and may include false positives.']}
(out/'build-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps(manifest,indent=2))
