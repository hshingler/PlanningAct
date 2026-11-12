#!/usr/bin/env python3
"""Build a static Planning Act knowledge website from a Logseq EDN datom export.
Usage: python build_site.py input.edn output-directory
"""
import ast, collections, html, json, re, shutil, sys, unicodedata, urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo
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
    target_patterns.append((target,title))
target_patterns.sort(key=lambda item: len(item[1]), reverse=True)
combined_titles=re.compile(r'(?<![\w])('+'|'.join(re.escape(t) for _,t in target_patterns)+r')(?![\w])',re.I) if target_patterns else None
title_lookup={t.casefold():target for target,t in target_patterns}
unlinked_refs=collections.defaultdict(list)
for bid,b in block_info.items():
    source_text=b['title']
    if not source_text or not combined_titles: continue
    source_refs={r for r in entities[bid].get('block/refs',[]) if isinstance(r,int)}
    matched_targets=set()
    for match in combined_titles.finditer(source_text):
        target=title_lookup.get(match.group(1).casefold())
        if not target or target['id'] in matched_targets or b['page_id']==target['id'] or source_refs.intersection({target['id']}|page_blocks.get(target['id'],set())): continue
        matched_targets.add(target['id'])
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

def render_legal_text(s, prefix=''):
    """Render parenthesized statutory markers with hanging text alignment."""
    rendered=[]
    marker_re=re.compile(r'^(?P<indent>[\u2003\u00a0 ]*)(?P<label>\((?:\d+|[a-z]|[ivxlcdm]+|[A-Z]|[IVXLCDM]+)\))\s*(?P<body>.*)$')
    for line in str(s).splitlines():
        match=marker_re.match(line)
        if not match:
            rendered.append(f'<div class="legal-text-line">{render_links(line,prefix)}</div>')
            continue
        depth=sum(1 for char in match.group('indent') if char in '\u2003\u00a0')
        depth=min(depth,5)
        indent_class=f' legal-line-indent-{depth}' if depth else ''
        rendered.append(
            f'<div class="legal-line{indent_class}"><span class="legal-label">'
            f'{render_links(match.group("label"),prefix)}</span><span class="legal-copy">'
            f'{render_links(match.group("body"),prefix)}</span></div>'
        )
    return ''.join(rendered) if rendered else render_links(s,prefix)

def reference_href(ref,from_root=False):
    prefix='pages/' if from_root else ''
    target=pages[ref['target_page_id']]
    focus='?focus='+urllib.parse.quote(target['title'])
    if ref['kind']=='page': return prefix+target['slug']+'.html'+focus
    b=block_info.get(ref['id'])
    if not b: return prefix+target['slug']+'.html'+focus
    return prefix+pages[b['page_id']]['slug']+'.html'+focus+'#block-'+(b['uuid'] or f'id-{b["id"]}')

def merge_references(page_id):
    merged={}
    for r in incoming_linked.get(page_id,{}).values():
        key=(r.get('page_id'),r.get('id')); item=dict(r); item['linked']=True; item['target_page_id']=page_id; item['text']=item.get('text') or item.get('title',''); merged[key]=item
    for r in unlinked_refs.get(page_id,[]):
        key=(r.get('page_id'),r.get('id'))
        if key not in merged:
            item=dict(r); item['linked']=False; item['target_page_id']=page_id; merged[key]=item
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
    return (f'<li class="reference-item" data-act="{source_act(ref)}" data-filter-text="{html.escape(searchable.casefold(),quote=True)}" data-start-text="{html.escape(excerpt.casefold(),quote=True)}">'
            f'<a href="{html.escape(href,quote=True)}">{html.escape(source_title)}</a> '
            f'<span class="reference-status {"linked" if ref["linked"] else "candidate"}">{"Linked" if ref["linked"] else "Possible match"}</span>{context_html}'
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
    interpretation=list({(r['page_id'],r['id']):r for r in items if is_interpretation(r)}.values())
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

def render_comparison_block(eid, desired, page_default='shared', inherited=None, ancestors=False):
    if eid not in block_info: return ''
    b=block_info[eid]
    own=block_act(eid) or inherited or page_default
    child_ids=children.get(eid,[])
    child_html=''.join(render_comparison_block(cid,desired,page_default,own) for cid in child_ids)
    # Keep a neutral ancestor as a lightweight context heading when it contains
    # material for this Act; its text is not otherwise duplicated as Act content.
    relevant=(own==desired) or bool(child_html)
    if not relevant: return ''
    uid=b['uuid'] or f'id-{eid}'
    context_class=' comparison-context' if own not in (desired,'shared') else ''
    toggle='<button class="block-toggle" type="button" aria-expanded="true" aria-label="Collapse block" title="Collapse/expand block">−</button>' if child_html else ''
    kids=f'<ul class="block-children">{child_html}</ul>' if child_html else ''
    return f'<li class="block-item{context_class}" id="block-{html.escape(uid)}">{toggle}<div class="block-text">{render_legal_text(b["title"])}</div>{kids}</li>'

def comparison_section(page_id):
    page_default=page_act(pages[page_id])
    roots=children.get(page_id,[])
    def tree_for(act):
        return ''.join(render_comparison_block(bid,act,page_default) for bid in roots)
    def refs_for(act):
        items=[r for r in merge_references(page_id) if source_act(r)==act]
        return reference_box('References and connections',items,False,True)
    pa_content=tree_for('pa'); nea_content=tree_for('nea')
    pa_refs=refs_for('pa'); nea_refs=refs_for('nea')
    shared_content=tree_for('shared'); npd_content=tree_for('npd')
    shared_refs=refs_for('shared'); npd_refs=refs_for('npd')
    def pane(title,act,content,refs):
        tree_html=f'<ul class="page-tree comparison-tree">{content}</ul>' if content else ''
        return f'<section class="act-column" data-act="{act}"><h2>{title}</h2>{tree_html}{refs}</section>'
    extras=''
    if shared_content or any(source_act(r)=='shared' for r in merge_references(page_id)):
        extras+=f'<section class="comparison-extra shared-material" data-act="shared"><h2>Shared material</h2><ul class="page-tree comparison-tree">{shared_content}</ul>{shared_refs}</section>'
    if npd_content or any(source_act(r)=='npd' for r in merge_references(page_id)):
        extras+=f'<section class="comparison-extra npd-material" data-act="npd"><h2>National Policy Direction</h2><ul class="page-tree comparison-tree">{npd_content}</ul>{npd_refs}</section>'
    controls='<div class="block-controls"><button type="button" class="button" id="expand-all">Expand all blocks</button> <button type="button" class="button" id="collapse-all">Collapse all blocks</button></div>'
    return '<section class="act-comparison">'+controls+'<div class="act-comparison-grid">'+pane('Planning Act 2026','pa',pa_content,pa_refs)+pane('Natural Environment Act 2026','nea',nea_content,nea_refs)+'</div>'+extras+'</section>'

def render_block(eid,seen,prefix=''):
    if eid in seen or eid not in block_info: return ''
    seen.add(eid); b=block_info[eid]; uid=b['uuid'] or f'id-{eid}'
    title_html=render_legal_text(b['title'],prefix)
    child_ids=children.get(eid,[]); kids=''.join(render_block(k,seen,prefix) for k in child_ids)
    toggle='<button class="block-toggle" type="button" aria-expanded="true" aria-label="Collapse block" title="Collapse/expand block">−</button>' if child_ids else ''
    child_html=f'<ul class="block-children">{kids}</ul>' if child_ids else ''
    return f'<li class="block-item" id="block-{html.escape(uid)}">{toggle}<div class="block-text">{title_html}</div>{child_html}</li>'

if out.exists(): shutil.rmtree(out)
(out/'pages').mkdir(parents=True, exist_ok=True); (out/'assets').mkdir(parents=True, exist_ok=True)
# Copy brand assets on every build so the deployment workflow cannot omit or erase them.
for asset_name in ('favicon.ico', 'favicon-16.png', 'favicon-32.png', 'favicon-48.png', 'favicon-64.png', 'favicon-180.png', 'favicon-192.png', 'favicon-512.png', 'apple-touch-icon.png'):
    source_asset = brand_assets / asset_name
    if source_asset.is_file():
        shutil.copy2(source_asset, out / asset_name)
    else:
        raise SystemExit(f'Missing required favicon asset: {source_asset}')
shutil.copy2(brand_assets / 'bosch-funnel-icon.png', out / 'assets' / 'bosch-funnel-icon.png')
shutil.copy2(brand_assets / 'planning-system-funnel.jpeg', out / 'assets' / 'planning-system-funnel.jpeg')

# Illustrated Funnel Folly essay images (supplied by the site owner).
essay_assets = out / 'assets' / 'funnel-essay'
essay_assets.mkdir(parents=True, exist_ok=True)
# Keep source copies inside the package: GitHub Actions runners do not have
# access to the original /mnt/data upload paths from the author's computer.
source_essay_assets = brand_assets / 'funnel-folly'
source_images = [
    'funnel-butt.jpg',
    'funnel-red-cloak.jpg',
    'funnel-barrel.jpg',
    'funnel-goose.jpg',
    'funnel-book.jpg',
    'funnel-figure.jpg',
    'removing-the-stone-detail.jpg',
]
for asset_name in source_images:
    source_image = source_essay_assets / asset_name
    if not source_image.is_file():
        raise SystemExit(f'Missing Funnel Folly image in package: {source_image}')
    shutil.copy2(source_image, essay_assets / asset_name)

def favicon_links(prefix=''):
    return (f'<link rel="icon" type="image/png" sizes="16x16" href="{prefix}favicon-16.png">'
            f'<link rel="icon" type="image/png" sizes="32x32" href="{prefix}favicon-32.png">'
            f'<link rel="icon" type="image/png" sizes="48x48" href="{prefix}favicon-48.png">'
            f'<link rel="icon" type="image/png" sizes="64x64" href="{prefix}favicon-64.png">'
            f'<link rel="shortcut icon" href="{prefix}favicon.ico">'
            f'<link rel="apple-touch-icon" sizes="180x180" href="{prefix}apple-touch-icon.png">')
css='''*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:20px}body{margin:0;background:#f5f1e7;color:#302f2a;font:16px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:#9a5b36;text-decoration:none;overflow-wrap:anywhere}a:hover{text-decoration:none;color:#6f3d25}.wrap{max-width:1500px;margin:auto;padding:24px 22px}.top{background:#62551c;color:#fff8e7}.top a{color:#fff8e7}.top .wrap{height:120px;min-height:120px;padding-top:8px;padding-bottom:8px;display:flex;align-items:center}.brand{font-weight:750;letter-spacing:.01em;font-size:1.1rem}.brand{display:flex;align-items:center;gap:14px}.brand-logo{width:104px;height:104px;object-fit:contain;border-radius:6px;flex:0 0 auto}.brand-logo-link{display:block;flex:0 0 auto;line-height:0}.funnel-essay{max-width:1180px;margin:0 auto 60px;padding-top:0}.funnel-layout{display:grid;grid-template-columns:minmax(150px,205px) minmax(0,1fr);gap:28px;align-items:start}.funnel-layout .essay-gallery{display:block;position:relative;overflow:hidden;margin:0;align-self:start;align-items:stretch;width:100%;min-width:0;height:250px}.essay-gallery figure{margin:0;background:transparent;border:0;padding:0;border-radius:0}.essay-gallery .essay-track{display:flex;width:max-content;height:100%;animation:folly-scroll 30s linear infinite}.essay-gallery figure{display:block;flex:0 0 205px;width:205px;height:100%;margin:0;padding:0;line-height:0;overflow:hidden}.essay-gallery figure img{width:100%;height:100%;object-fit:cover}.essay-gallery:hover .essay-track{animation-play-state:paused}@keyframes folly-scroll{from{transform:translateX(0)}to{transform:translateX(-50%)}}.essay-gallery img{display:block;width:100%;height:100%;object-fit:cover;margin:0;padding:0;border:0}.funnel-layout .essay-copy{max-width:790px;min-width:0;overflow-wrap:anywhere;word-break:normal;font-family:Georgia,serif;font-size:1.16rem;line-height:1.78}.funnel-essay p{margin:0 0 1.45em}.essay-final-image{margin:1.5rem 0 1.75rem;max-width:360px}.essay-final-image img{display:block;width:100%;height:auto}.essay-return{display:inline-block;margin:12px 0 30px;padding:9px 13px;border:1px solid #b9ad82;border-radius:5px;color:#51491f;font-weight:650}.essay-return:hover{background:#e9e1c8}@media(max-width:760px){.funnel-layout{grid-template-columns:1fr;gap:18px}.funnel-layout .essay-gallery{display:block;width:100%;height:190px;margin:0}.essay-gallery figure{flex-basis:190px;width:190px}.essay-gallery img{width:100%;height:100%;max-height:none}.funnel-layout .essay-copy{font-size:1.08rem}}.home-header{display:grid;grid-template-columns:104px minmax(0,1fr);align-items:center;gap:20px}.home-header-content{min-width:0}.brand-title{font-weight:750;letter-spacing:.01em;font-size:.98rem;line-height:1.25;margin-bottom:5px}.home-header-main{display:flex;align-items:center;justify-content:space-between;gap:22px;min-width:0}.home-header-main h1{font-size:clamp(1.35rem,2.3vw,2rem);line-height:1.1;margin:0;max-width:560px}.hero{padding:0;min-width:0;flex:1}.hero p{display:none}.search{display:flex;gap:8px;margin:0;max-width:580px;flex:1;min-width:260px}.search input,.sidebar-search input{flex:1;min-width:0;padding:9px 12px;border:1px solid #d7d0bf;border-radius:7px;font:inherit}.search button,.button{padding:9px 12px;border:1px solid #d7d0bf;border-radius:7px;background:#e8e0cc;color:#403f36;font-weight:650;cursor:pointer}.layout{display:grid;grid-template-columns:260px minmax(0,1fr);gap:24px;align-items:start}.panel,.content-card{background:#fffdf8;border:1px solid #ded6c4;border-radius:9px;padding:18px;min-width:0}.panel h2,.content-card h2{margin-top:0}.sidebar{position:sticky;top:12px;max-height:calc(100vh - 24px);overflow:auto}.navlist{padding:0;list-style:none}.navlist li{margin:.55rem 0}.muted{color:#68746e}.small{font-size:.88rem}.result{background:white;border:1px solid #e1e5e1;border-radius:10px;padding:14px}.pill{display:inline-block;background:#eef2ef;color:#47544d;border-radius:99px;padding:2px 8px;font-size:.78rem;margin:2px 4px 2px 0}.tag{display:inline-block;background:transparent;border:1px solid #d7c9a6;color:#75694f;border-radius:3px;padding:1px 6px;font-size:.75rem;margin:2px 4px 2px 0;white-space:normal}.crumb{font-size:.88rem;color:#65716b;margin-bottom:12px}.page-title{font-size:clamp(1.8rem,4vw,2.5rem);line-height:1.15;margin:.2rem 0 1rem}.page-tree{padding-left:1.35rem}.page-tree>li{padding:.25rem 0}.page-tree ul{padding-left:1.4rem;margin:.35rem 0}.block-item{position:relative;padding:.18rem 0}.block-text{white-space:pre-wrap;overflow-wrap:anywhere}.block-toggle{position:absolute;left:-1.55rem;top:.18rem;width:1.2rem;height:1.35rem;display:inline-flex;align-items:center;justify-content:center;padding:0;border:1px solid #d6ddd8;border-radius:4px;background:#f5f7f5;color:#31564a;font-size:.9rem;line-height:1;cursor:pointer;z-index:1}.block-toggle:hover{background:#e5eee8}.block-children{margin:.3rem 0 .25rem;padding-left:1.4rem}.tags{margin-top:5px}.empty{padding:18px;border:1px dashed #cbd4cf;border-radius:10px;color:#65716b}.footer{margin-top:42px;padding-top:18px;border-top:1px solid #dce2dd;color:#65716b;font-size:.85rem}.reference-section{margin-top:22px;min-width:0}.reference-box{background:#fffdf8;border:1px solid #ded6c4;border-radius:8px;padding:14px;min-width:0;width:100%;overflow-wrap:anywhere}.reference-box h3{margin:0 0 10px;font-size:1rem}.ref-count{display:inline-block;background:#eee6d2;border-radius:3px;padding:1px 7px;font-size:.8rem;margin-left:6px}.reference-list{list-style:none;padding:0;margin:0;min-width:0}.reference-item{border-top:1px solid #eee8dc;padding:12px 0;min-width:0;overflow-wrap:anywhere}.reference-item:first-child{border-top:0}.reference-context{margin:5px 0 2px;color:#9a968b;font-size:.78rem;line-height:1.4;overflow-wrap:anywhere;word-break:normal}.reference-item .reference-extract{margin:2px 0 0;color:#59665f;font-size:.92rem;overflow-wrap:anywhere;word-break:normal}.ref-empty{color:#65716b;font-size:.92rem;margin:.4rem 0}.section-heading{margin:25px 0 10px}.home-content{margin-top:18px}.reference-filter{width:100%;padding:9px 10px;margin:0 0 10px;border:1px solid #d7d0bf;border-radius:7px;font:inherit}.instrument-reference-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:14px;align-items:start;width:100%;min-width:0}.instrument-reference-grid>*{min-width:0;width:100%}.search-highlight{background:#ffef70;color:#202522;border-radius:2px;padding:0 .03em}.search-group{margin:18px 0;min-width:0}.search-group h2{font-size:1.15rem;margin:.2rem 0 .7rem}.search-group-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;min-width:0}.search-group-grid>.search-group .search-group-grid{grid-template-columns:minmax(0,1fr);gap:10px}.search-group-grid>.search-group .search-ref{width:100%;min-width:0}.search-ref{background:#fffdf8;border:1px solid #ded6c4;border-radius:8px;padding:12px;min-width:0;overflow-wrap:anywhere}.search-ref h3{font-size:.98rem;margin:0 0 5px}.search-ref p{font-size:.91rem;margin:.3rem 0;color:#59665f;overflow-wrap:anywhere}.search-other-filter{width:100%;padding:10px;border:1px solid #cbd4cf;border-radius:7px;font:inherit;margin:0 0 10px}.sidebar-home{display:block;text-align:center;margin-bottom:14px}.inner-header{display:flex;align-items:center;gap:16px;height:104px;min-height:104px;width:100%}.inner-header .brand-title{margin:0;white-space:nowrap;font-size:clamp(1.35rem,2.3vw,2rem);line-height:1.1;max-width:560px}.inner-search{margin-left:auto}.header-legislation{display:flex;align-items:center;gap:12px;flex:0 0 auto;font-size:.82rem;line-height:1.25}.header-legislation a{text-decoration:underline;text-underline-offset:3px;white-space:nowrap}.page-tags{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:12px}.home-content .block-controls{margin-bottom:12px}.sidebar-search button{border:1px solid #d7d0bf;background:#e8e0cc;border-radius:7px;padding:8px;cursor:pointer}.side-section{border-top:1px solid #e8e0d0;padding-top:12px;margin-top:14px}.side-section h3{font-size:.92rem;margin:0 0 8px}.side-tree{list-style:none;padding-left:12px;margin:0}.side-tree li{margin:4px 0}.side-tree details>summary{cursor:pointer;color:#47594e;font-weight:650}.side-tree a{font-size:.9rem}.recent-list{padding-left:18px;margin:0}.recent-list li{margin:5px 0;font-size:.9rem}.page-jump{position:fixed;right:16px;top:50%;transform:translateY(-50%);z-index:50;display:flex;flex-direction:column;gap:7px}.page-jump a{display:flex;align-items:center;justify-content:center;width:42px;height:42px;border:1px solid #d7c9a6;border-radius:8px;background:#fffdf8;color:#31564a;text-decoration:none;box-shadow:0 2px 8px #00000012;font-size:1.1rem}.page-jump a:hover{background:#e8e0cc}@media(max-width:1100px){.home-header-main{align-items:flex-start;flex-direction:column;gap:8px}.search{max-width:680px;width:100%}}@media(max-width:900px){.layout{grid-template-columns:220px minmax(0,1fr);gap:14px}.wrap{padding:18px 14px}.top .wrap{padding:8px 14px}.instrument-reference-grid,.search-group-grid{grid-template-columns:1fr}}@media(max-width:680px){.inner-header{flex-wrap:wrap;gap:10px}.header-legislation{order:3;flex-basis:100%;flex-wrap:wrap}.inner-search{order:4}.inner-header .brand-title{white-space:normal}.inner-search{flex-basis:100%;max-width:none;margin-left:0}.essay-gallery{gap:10px}.essay-gallery .wide,.essay-gallery .narrow,.essay-gallery .half{grid-column:1/-1}.funnel-essay .essay-copy{font-size:1.05rem}.home-header{grid-template-columns:76px minmax(0,1fr);gap:12px}.brand-logo{width:76px;height:76px}.home-header-main h1{font-size:1.25rem}.layout{grid-template-columns:1fr}.sidebar{position:relative;top:auto;max-height:none}.search{flex-direction:column;min-width:0}.search button{width:100%}.page-jump{right:8px}.page-jump a{width:36px;height:36px}}'''

css += """
/* Version 9 editorial design */
body{background:#f4f0e6;color:#302e29;font-family:Georgia,'Times New Roman',serif}
.top{background:#f4f0e6;color:#302e29;border-bottom:1px solid #c9c1b2}.top a{color:#655c4d}
.brand-lockup{display:flex;flex-direction:column;gap:3px;min-width:0}.brand-title,.home-header-main h1{font-family:Georgia,serif;font-weight:600;letter-spacing:.055em;color:#302e29}.brand-subtitle{font:600 .68rem/1.2 system-ui,sans-serif;letter-spacing:.18em;color:#8a7d68}
.brand-logo{width:82px;height:82px}.top .wrap{height:100px;min-height:100px}.inner-header{height:84px;min-height:84px}.header-legislation{margin-left:auto}.header-legislation a{color:#645a4b;font-size:.78rem}
.panel,.content-card,.reference-box,.result,.search-ref{background:transparent;border:0;border-radius:0;box-shadow:none}.panel{padding:8px 14px 8px 0}.content-card{padding:0}.sidebar{border-right:1px solid #d9d1c2}.side-section{border-top:1px solid #d8d0c2}.side-section h3{font:600 .72rem system-ui,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:#867966}.navlist a,.side-tree a,.recent-list a{color:#5b574e}.navlist li{margin:.35rem 0}.recent-list{padding-left:17px}.recent-list li{font-size:.84rem}.main-topline{display:flex;align-items:center;justify-content:space-between;gap:18px;margin:0 0 18px;padding-bottom:10px;border-bottom:1px solid #d9d1c2}.view-switch{display:flex;gap:18px;align-items:center;margin-left:auto;font:600 .78rem system-ui,sans-serif}.view-switch a{color:#625b4f;padding:5px 0;border-bottom:1px solid transparent}.view-switch a:hover{color:#267f80;border-color:#267f80}.view-switch a:last-child{color:#a34f3f}.page-title{font-family:Georgia,serif;font-weight:500;letter-spacing:-.02em}.block-text{font-family:Georgia,serif}.tag{border:0;border-bottom:1px solid #c7b89b;border-radius:0;color:#85765d;padding:0 2px}.reference-box{border-top:1px solid #d8d0c2;padding:12px 0}.reference-item{border-color:#e6dfd2}.reference-item a{color:#287d7e}.button,.search button{border-radius:0;background:transparent;border:1px solid #c9c0ae;color:#554d40}.search input{border-radius:0;background:#fffdf8}.search button#clear-search{color:#625b4f;background:transparent}.sidebar-home{display:block;text-align:center;padding:8px 10px;border:1px solid #c9c0ae;color:#554d40;margin:0 0 12px;font-weight:650}.sidebar-view-switch{display:flex;flex-direction:column;gap:5px}.sidebar-view-switch a{color:#5b574e;padding:3px 0}.sidebar-view-switch a.active{font-weight:700;color:#267f80;border-bottom:1px solid #267f80}.official-label{font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;opacity:.9}.header-legislation{flex-direction:column;align-items:flex-end;gap:4px}.inner-header{display:grid;grid-template-columns:auto auto minmax(240px,1fr) auto;gap:18px}.inner-search{grid-column:3;margin:0;width:100%;max-width:620px;justify-self:center}.home-header-main{display:grid;grid-template-columns:auto minmax(260px,1fr) auto;gap:24px}.home-header-main .search{width:100%;max-width:620px;justify-self:center}.act-view-notice{padding:12px 0;border-top:1px solid #d8d0c2;border-bottom:1px solid #d8d0c2}.reference-item[hidden],.content-card[hidden],.reference-section[hidden]{display:none!important}.fixed-nav{border-top:1px solid #bdb29e}.home-content{margin-top:20px}.home-content h2{font-family:Georgia,serif;font-weight:500}.footer{border-color:#d8d0c2;color:#8a8173}
.both-toolbar{height:76px;display:flex;align-items:center;gap:20px;padding:10px 24px;border-bottom:1px solid #c9c1b2;background:#f4f0e6}.both-brand{font:600 .92rem Georgia,serif;letter-spacing:.06em}.both-brand small{display:block;font:600 .62rem system-ui,sans-serif;letter-spacing:.18em;color:#8a7d68;margin-top:3px}.both-controls{margin-left:auto;display:flex;gap:16px;font:600 .78rem system-ui,sans-serif}.both-controls a{color:#625b4f}.both-panels{display:flex;height:calc(100vh - 76px);min-height:500px;overflow:hidden}.both-pane{flex:1 1 50%;min-width:0;height:100%;border:0;background:#f4f0e6}.both-divider{width:7px;flex:0 0 7px;cursor:col-resize;background:#d7cdbc;position:relative}.both-divider:after{content:'';position:absolute;top:50%;left:2px;height:52px;width:3px;transform:translateY(-50%);background:#8f8574}
body.pane-mode .top,body.pane-mode .sidebar,body.pane-mode .page-jump,body.pane-mode .footer{display:none!important}body.pane-mode main.wrap{max-width:none;padding:22px 26px}body.pane-mode .layout{display:block}body.pane-mode .main-column{width:100%;max-width:900px;margin:0 auto}body.pane-mode .main-topline{display:none}
@media(max-width:850px){.both-panels{flex-direction:column}.both-divider{width:100%;height:7px;flex-basis:7px;cursor:row-resize}.both-pane{min-height:0}.home-header{grid-template-columns:76px minmax(0,1fr)}.brand-logo{width:70px;height:70px}}
"""

css += """
@media(max-width:900px){
 .inner-header{grid-template-columns:auto minmax(0,1fr);height:auto;min-height:0;padding:12px 0}
 .inner-search{grid-column:1/-1;grid-row:2;max-width:none}
 .header-legislation{grid-column:1/-1;grid-row:3;align-items:flex-start;margin:0}
 .home-header-main{grid-template-columns:1fr;gap:12px}
 .home-header-main .search{grid-column:1;grid-row:2;max-width:none}
 .home-header-main .header-legislation{grid-column:1;grid-row:3;align-items:flex-start}
}
"""
css += '''\n.home-welcome{max-width:920px;margin:30px auto 50px}.home-welcome h1{font-size:clamp(2rem,4vw,3rem);font-weight:500;margin:0 0 14px}.home-welcome p{font-size:clamp(1.1rem,2vw,1.35rem);line-height:1.65;max-width:850px}.home-welcome figure{margin:28px 0 0}.home-welcome img{display:block;width:100%;height:auto;border:1px solid #d8d0c2}.home-welcome figcaption{margin-top:8px;color:#817867;font:.82rem system-ui,sans-serif}.home-welcome[hidden]{display:none!important}\n.reference-status{display:inline-block;margin-left:5px;padding:1px 6px;font:600 .65rem/1.5 system-ui,sans-serif;letter-spacing:.02em;vertical-align:middle}.reference-status.linked{color:#386b55;background:#e6eee7}.reference-status.candidate{color:#865b2c;background:#f3ead7}.view-switch a.active{font-weight:750;color:#267f80;border-bottom-color:#267f80}
/* 2.1.0: consistent editorial header and side-by-side Act comparison */\n.inner-header{display:grid;grid-template-columns:104px minmax(190px,auto) minmax(260px,1fr) auto;align-items:center;gap:18px;height:104px;min-height:104px;width:100%}.inner-header .brand-logo{width:92px;height:92px}.inner-header .brand-lockup{min-width:0}.inner-header .brand-title{display:block;font-weight:750;letter-spacing:.01em;font-size:1.02rem;line-height:1.25;margin:0 0 4px}.brand-subtitle{display:block;font-size:.68rem;letter-spacing:.13em;text-transform:uppercase;opacity:.85}.inner-search{grid-column:auto;margin:0;width:100%;max-width:620px;justify-self:center}.header-legislation{display:flex;flex-direction:column;align-items:flex-end;gap:4px;white-space:nowrap}.act-comparison{margin-top:18px}.act-comparison-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:30px;align-items:start}.act-column{min-width:0;padding:0 16px 0 0;border-right:1px solid #d8d0c2}.act-column:last-child{padding:0 0 0 16px;border-right:0}.act-column h2,.comparison-extra h2{font:500 1.35rem/1.25 Georgia,serif;margin:0 0 16px;padding-bottom:10px;border-bottom:1px solid #d8d0c2}.comparison-tree{padding-left:1.35rem}.act-column .reference-section{margin-top:20px}.act-column .reference-box{border-top:1px solid #d8d0c2}.comparison-extra{margin-top:26px;padding-top:18px;border-top:1px solid #cfc5b2}.comparison-extra .page-tree{margin-bottom:18px}.comparison-context>.block-text{color:#807766;font-style:italic}.comparison-context>.tags{opacity:.7}.act-column[hidden],.comparison-extra[hidden]{display:none!important}.funnel-folly-page .inner-header{display:flex;align-items:center;gap:16px;height:104px;min-height:104px;width:100%}.funnel-folly-page .inner-header .brand-logo{width:104px;height:104px}.funnel-folly-page .inner-header .brand-title{font-size:clamp(1.35rem,2.3vw,2rem);margin:0;white-space:nowrap}.funnel-folly-page .inner-header .brand-subtitle{font-size:.68rem}@media(max-width:900px){.act-comparison-grid{grid-template-columns:1fr;gap:22px}.act-column,.act-column:last-child{padding:0;border:0}.act-column+ .act-column{padding-top:20px;border-top:1px solid #d8d0c2}.inner-header{grid-template-columns:76px minmax(0,1fr);height:auto;min-height:0;padding:8px 0}.inner-header .brand-logo{width:72px;height:72px}.inner-search{grid-column:1/-1;max-width:none}.header-legislation{grid-column:1/-1;align-items:flex-start;flex-direction:row;flex-wrap:wrap;white-space:normal}.brand-lockup{grid-column:2;grid-row:1}}\n'''
css += '''\n.legal-line{display:grid;grid-template-columns:max-content minmax(0,1fr);column-gap:.5em;align-items:start}.legal-label{white-space:nowrap}.legal-copy{min-width:0}.legal-line-indent-1{margin-left:1.45em}.legal-line-indent-2{margin-left:2.9em}.legal-line-indent-3{margin-left:4.35em}.legal-line-indent-4{margin-left:5.8em}.legal-line-indent-5{margin-left:7.25em}.legal-text-line{display:block}\n'''
css += '@media(max-width:900px){.header-legislation{grid-column:2;grid-row:1;align-items:flex-end;flex-direction:column;flex-wrap:nowrap;white-space:nowrap}.inner-search{grid-row:2}}.home-view-switch{display:flex;justify-content:flex-end;margin:0 0 14px}'
css += '''
/* Horizontal file-divider tabs for the legislation view links */
.view-switch{gap:3px;align-items:flex-end;border-bottom:1px solid #8f887b;font:600 .78rem/1.2 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.view-switch a,.view-switch a:last-child{position:relative;padding:8px 13px 7px;border:1px solid #8f887b;border-bottom:0;border-radius:11px 11px 0 0;background:#eeeadd;color:#403c34;text-decoration:none;white-space:nowrap;z-index:0}
.view-switch a::before{content:"";position:absolute;left:10px;right:10px;top:-1px;height:1px;background:#8f887b}
.view-switch a:hover{background:#e5dfcf;color:#302e29;border-color:#625b4f}
.view-switch a.active{padding-top:11px;margin-bottom:-1px;border-color:#625b4f;background:#fffdf8;color:#302e29;font-weight:700;z-index:1}
.view-switch a.active::before{background:#625b4f}
@media(max-width:520px){.view-switch{gap:2px;flex-wrap:nowrap;overflow-x:auto;justify-content:flex-start}.view-switch a,.view-switch a:last-child{padding:7px 9px 6px;font-size:.72rem}.view-switch a.active{padding-top:9px}}
'''
(out/'assets/style.css').write_text(css,encoding='utf-8')

# Search index includes full page text and graph tags for grouped search results.
def tagged_act(tag_ids):
    labels={str(x).casefold().replace(' ','') for x in tag_titles(tag_ids)}
    if 'pa2026' in labels or 'planningact2026' in labels: return 'pa'
    if 'nea2026' in labels or 'naturalenvironmentact2026' in labels: return 'nea'
    if 'npd' in labels or 'nationalpolicydirection' in labels: return 'npd'
    return None

def page_act(p):
    return tagged_act(p.get('tags',[])) or 'shared'

def block_act(bid, fallback='shared'):
    seen=set()
    while bid in block_info and bid not in seen:
        seen.add(bid)
        b=block_info[bid]
        own=tagged_act(b.get('tags',[]))
        if own: return own
        parent=b.get('parent')
        bid=parent if parent in block_info else None
    return None

def source_act(ref):
    if ref.get('kind') == 'block':
        own=block_act(ref.get('id'))
        if own: return own
    return page_act(pages[ref['page_id']])

search_records=[]
for p in pages.values():
    block_ids=[]; seen=set()
    def walk(pid):
        for bid in children.get(pid,[]):
            if bid in seen: continue
            seen.add(bid); block_ids.append(bid); walk(bid)
    walk(p['id']); body=' '.join(block_info[bid]['title'] for bid in block_ids)
    search_records.append({'title':p['title'],'slug':p['slug'],'name':p['name'],'tags':tag_titles(p['tags']),'act':page_act(p),'text':clean_text(body)[:50000]})
(out/'assets'/'search-index.json').write_text(json.dumps(search_records,ensure_ascii=False),encoding='utf-8')

page_script=r'''<script>
function escSidebar(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function recentKey(item){try{const url=new URL(item.href,location.href);url.searchParams.delete('view');return url.pathname+url.search+url.hash}catch(e){return item.href}}function isDedicatedRecent(item){try{const url=new URL(item.href,location.href),path=url.pathname.replace(/\/$/,'');const actLanding=path.endsWith('/index.html')&&['pa','nea'].includes(url.searchParams.get('view'))&&!url.searchParams.has('q')&&!url.searchParams.has('focus');const contents=['/pages/planning-act-2026-contents.html','/pages/natural-environment-act-2026-contents.html','/pages/illustrative-national-policy-direction-contents.html'].some(s=>path.endsWith(s));return actLanding||contents}catch(e){return false}}function saveRecent(item){const key='pa-recent-pages-v6';let items=[];try{items=JSON.parse(localStorage.getItem(key)||'[]')}catch(e){}const itemKey=recentKey(item);items=[item,...items.filter(x=>recentKey(x)!==itemKey)].filter(x=>!isDedicatedRecent(x)).slice(0,10);try{localStorage.setItem(key,JSON.stringify(items))}catch(e){}const list=document.getElementById('recent-pages');if(list)list.innerHTML=items.map(x=>'<li><a href="'+escSidebar(x.href)+'">'+(x.type==='search'?'Search: ':'')+escSidebar(x.title)+'</a></li>').join('')}function bindRecentPages(){const list=document.getElementById('recent-pages');if(!list)return;let items=[];try{items=JSON.parse(localStorage.getItem('pa-recent-pages-v6')||'[]')}catch(e){}items=items.filter(x=>!isDedicatedRecent(x));try{localStorage.setItem('pa-recent-pages-v6',JSON.stringify(items))}catch(e){}const current=document.querySelector('h1.page-title');if(current){const title=current.textContent.trim(),href=location.pathname+location.search+location.hash;if(!isDedicatedRecent({href}))saveRecent({title,href,type:'page'});try{items=JSON.parse(localStorage.getItem('pa-recent-pages-v6')||'[]')}catch(e){}}list.innerHTML=items.length?items.map(x=>'<li><a href="'+escSidebar(x.href)+'">'+(x.type==='search'?'Search: ':'')+escSidebar(x.title)+'</a></li>').join(''):'<li class="muted small">Pages and searches will appear here.</li>'}
function normalizeActView(value){return ['pa','nea','both'].includes(value)?value:'both'}
function selectedActView(){return normalizeActView(new URLSearchParams(location.search).get('view'))}
function applyActView(){const params=new URLSearchParams(location.search),page=document.querySelector('.main-column[data-page-act]'),mode=normalizeActView(params.get('view')||(page&&page.dataset.defaultView? page.dataset.defaultView : (page&&page.dataset.pageAct!=='shared'?page.dataset.pageAct:'both')));document.body.dataset.actView=mode;document.querySelectorAll('.sidebar-view-switch a,.view-switch a,.fixed-nav a[data-view]').forEach(a=>{const selected=a.dataset.view===mode;a.classList.toggle('active',selected);if(selected)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current')});document.querySelectorAll('form.search').forEach(form=>{let field=form.querySelector('input[name="view"]');if(!field){field=document.createElement('input');field.type='hidden';field.name='view';form.appendChild(field)}field.value=mode});document.querySelectorAll('a[data-preserve-view]').forEach(a=>{const target=new URL(a.href,location.href);target.searchParams.set('view',mode);a.href=target.href});document.querySelectorAll('.act-column[data-act]').forEach(col=>{col.hidden=mode!=='both'&&col.dataset.act!==mode});document.querySelectorAll('.comparison-extra[data-act]').forEach(section=>{section.hidden=false});if(page&&!page.querySelector('.act-comparison')){const mismatch=mode!=='both'&&page.dataset.pageAct!=='shared'&&page.dataset.pageAct!==mode,card=page.querySelector('.content-card'),refs=page.querySelector('.reference-section');if(card)card.hidden=mismatch;if(refs)refs.hidden=mismatch;let note=page.querySelector('.act-view-notice');if(mismatch&&!note){note=document.createElement('p');note.className='act-view-notice muted';note.textContent='This page belongs to the other Act. Change the view above to see its content.';page.insertBefore(note,page.querySelector('.page-tags')?.nextSibling||page.firstChild)}if(note)note.hidden=!mismatch}document.querySelectorAll('.reference-item[data-act]').forEach(item=>{item.hidden=mode!=='both'&&item.dataset.act!=='shared'&&item.dataset.act!=='npd'&&item.dataset.act!==mode})}
function bindBlockToggles(){document.querySelectorAll('.block-toggle').forEach(btn=>btn.addEventListener('click',()=>{const li=btn.closest('.block-item');const kids=li.querySelector(':scope > .block-children');if(!kids)return;const open=btn.getAttribute('aria-expanded')==='true';kids.hidden=open;btn.setAttribute('aria-expanded',String(!open));btn.textContent=open?'+':'−';btn.setAttribute('aria-label',open?'Expand block':'Collapse block')}));const ex=document.getElementById('expand-all'),co=document.getElementById('collapse-all');if(ex)ex.addEventListener('click',()=>document.querySelectorAll('.block-item > .block-children').forEach(ul=>{ul.hidden=false;const b=ul.parentElement.querySelector(':scope > .block-toggle');if(b){b.textContent='−';b.setAttribute('aria-expanded','true');b.setAttribute('aria-label','Collapse block')}}));if(co)co.addEventListener('click',()=>document.querySelectorAll('.block-item > .block-children').forEach(ul=>{ul.hidden=true;const b=ul.parentElement.querySelector(':scope > .block-toggle');if(b){b.textContent='+';b.setAttribute('aria-expanded','false');b.setAttribute('aria-label','Expand block')}}))}
function bindReferenceFilters(){document.querySelectorAll('.reference-filter').forEach(input=>input.addEventListener('input',()=>{const box=input.closest('.reference-box'),q=input.value.trim().toLowerCase(),starts=box.dataset.filterMode==='starts';box.querySelectorAll('.reference-item').forEach(item=>{const hay=starts?(item.dataset.startText||''):(item.dataset.filterText||'');item.hidden=starts?!hay.startsWith(q):!hay.includes(q)})}))}
if(new URLSearchParams(location.search).has("pane"))document.body.classList.add("pane-mode");
function highlightQuery(){const params=new URLSearchParams(location.search),q=params.get('q')||params.get('focus');if(!q)return;const terms=q.trim().split(/\s+/).filter(Boolean).sort((a,b)=>b.length-a.length),patterns=terms.map(t=>new RegExp(t.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'gi')),root=document.querySelector('main')||document.body,walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentElement&&!['SCRIPT','STYLE','MARK','INPUT','TEXTAREA'].includes(n.parentElement.tagName)&&terms.some(t=>n.nodeValue.toLowerCase().includes(t.toLowerCase()))?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT}),nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);nodes.forEach(node=>{const text=node.nodeValue,frag=document.createDocumentFragment();let i=0;while(i<text.length){let found=null,matchIndex=text.length;for(const re of patterns){re.lastIndex=i;const m=re.exec(text);if(m&&m.index<matchIndex){found=m;matchIndex=m.index}}if(!found){frag.appendChild(document.createTextNode(text.slice(i)));break}if(matchIndex>i)frag.appendChild(document.createTextNode(text.slice(i,matchIndex)));const mark=document.createElement('mark');mark.className='search-highlight';mark.textContent=found[0];frag.appendChild(mark);i=matchIndex+found[0].length}node.parentNode.replaceChild(frag,node)});const first=root.querySelector('.search-highlight');if(first)setTimeout(()=>first.scrollIntoView({behavior:'smooth',block:'center'}),120)}
applyActView();document.addEventListener('click',ev=>{const a=ev.target.closest('.view-switch a[data-view],.sidebar-view-switch a[data-view],.fixed-nav a[data-view]');if(!a)return;ev.preventDefault();const target=new URL(location.href);target.searchParams.set('view',normalizeActView(a.dataset.view));location.href=target.href});bindBlockToggles();bindReferenceFilters();bindRecentPages();highlightQuery();document.querySelectorAll('.side-provision-toggle').forEach(b=>b.addEventListener('click',()=>{const d=b.nextElementSibling;if(d)d.open=!d.open}));
</script>'''

# Shared left navigation: search, recent pages, graph exploration, and collapsible provision hierarchy.
provision_pages=[p for p in pages.values() if page_has_tag(p['id'],'provision')]
act_pages={p['slug']:page_act(p) for p in pages.values()}
part_pages=[p for p in pages.values() if re.match(r'^(part|subpart)\s+[0-9ivxlcdm]+',p['title'].strip(),re.I)]
def nav_href(p,from_root=False): return ('../' if from_root else '')+'pages/'+p['slug']+'.html'
def sidebar_html(from_root=False):
    prefix='../' if from_root else ''
    planning_contents_href=prefix+'pages/planning-act-2026-contents.html'
    nea_contents_href=prefix+'pages/natural-environment-act-2026-contents.html'
    provision_items=sorted(provision_pages,key=lambda p:statutory_sort_key(p['title']))
    groups=collections.OrderedDict()
    for p in provision_items:
        m=re.match(r'^(Part\\s+[0-9ivxlcdm]+[^:–—-]*|Subpart\\s+[0-9ivxlcdm]+[^:–—-]*)',p['title'].strip(),re.I)
        key=m.group(1) if m else 'All provisions'
        if key == 'All provisions': continue
        groups.setdefault(key,[]).append(p)
    tree=[]
    for label,items in groups.items():
        tree.append('<li><details><summary>'+html.escape(label)+' ('+str(len(items))+')</summary><ul class="side-tree">'+''.join('<li><a href="'+nav_href(p,from_root)+'">'+html.escape(p['title'])+'</a></li>' for p in items)+'</ul></details></li>')
    return f'''<aside class="panel sidebar"><a class="sidebar-home" href="{prefix}index.html">Home</a><section class="side-section fixed-nav"><h3>Contents</h3><ul class="navlist"><li><a href="{planning_contents_href}">Planning Act</a></li><li><a href="{nea_contents_href}">Natural Environment Act</a></li><li><a href="{prefix}pages/illustrative-national-policy-direction-contents.html" data-preserve-view>National policy direction</a></li></ul></section><section class="side-section recent-section"><h3>Recently visited</h3><ol class="recent-list" id="recent-pages"><li class="muted small">Pages and searches will appear here.</li></ol></section><section class="side-section"><h3>Explore</h3><ul class="navlist"><li><a href="{prefix}actors.html">Actors</a></li><li><a href="{prefix}concepts-expressions.html">Concepts</a></li><li><a href="{prefix}planning-instruments.html">Instruments</a></li></ul></section>{('<section class="side-section"><h3>Provisions</h3><ul class="side-tree">'+''.join(tree)+'</ul></section>') if tree else ''}</aside>'''


# Render individual pages. Concept and actor pages use special reference grouping.
for p in pages.values():
    seen=set(); tree=''.join(render_block(bid,seen) for bid in children.get(p['id'],[]))
    tags=''.join(f'<span class="tag">{html.escape(str(t))}</span>' for t in tag_titles(p['tags']) if t)
    is_comparison=is_concept_or_actor(p)
    refs_html=reference_section(p['id'],grouped=is_comparison)
    controls='<button type="button" class="button" id="expand-all">Expand all blocks</button> <button type="button" class="button" id="collapse-all">Collapse all blocks</button>'
    empty_tree='<li class="muted">No child blocks were found for this page.</li>'
    page_tree=tree or empty_tree
    page_content=(comparison_section(p['id']) if is_comparison else f'<section class="content-card"><div class="block-controls">{controls}</div><ul class="page-tree">{page_tree}</ul></section>{refs_html}')
    body=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(p['title'])} · NZ Planning System</title>{favicon_links('../')}<link rel="stylesheet" href="../assets/style.css"></head><body><header class="top"><div class="wrap"><div class="inner-header"><a class="brand-logo-link" href="../funnel-folly.html" aria-label="The Funnel Folly"><img class="brand-logo" src="../assets/bosch-funnel-icon.png" alt="Funnel Folly creature"></a><div class="brand-lockup"><span class="brand-title">NZ PLANNING SYSTEM</span><span class="brand-subtitle">LEGAL KNOWLEDGE BASE</span></div><form class="search inner-search" action="../index.html" method="get"><input type="search" name="q" placeholder="Search provisions, concepts, expressions or actors…" aria-label="Search"><button type="submit">Search</button><button type="button" id="clear-search">Clear</button></form><nav class="header-legislation" aria-label="Official legislation"><span class="official-label">Official Legislation:</span><a href="https://www.legislation.govt.nz/act/public/2026/70/en/latest/#LMS1035807" target="_blank" rel="noopener">Planning Act 2026</a><a href="https://www.legislation.govt.nz/act/public/2026/71/en/latest/#LMS1520775" target="_blank" rel="noopener">Natural Environment Act 2026</a></nav></div></div></header><main class="wrap"><div class="layout">{sidebar_html(True)}<section class="main-column" data-page-act="{page_act(p)}" data-default-view="{'both' if is_comparison else page_act(p)}"><h1 class="page-title">{html.escape(p['title'])}</h1><div class="page-tags">{tags or '<a href="../index.html">Home</a>'}</div>{page_content}<div class="footer">Generated from the supplied Logseq EDN export · Site built {datetime.now(ZoneInfo('Pacific/Auckland')).strftime('%d %B %Y')}. Confirm statutory wording and context against official legislation.</div></section></div><nav class="page-jump" aria-label="Page navigation"><a href="#" aria-label="Go to top" title="Go to top">↑</a><a href="#page-bottom" aria-label="Go to bottom" title="Go to bottom">↓</a></nav><span id="page-top"></span><span id="page-bottom"></span></main>{page_script}</body></html>'''
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
    is_explore_page=cat['slug'] in {'actors','concepts-expressions','planning-instruments'}
    toggle_html='' if is_explore_page else '<nav class="view-switch"><a href="index.html?view=pa" data-view="pa">Planning Act</a><a href="index.html?view=nea" data-view="nea">Natural Environment Act</a><a href="index.html?view=both" data-view="both">Both</a></nav>'
    return_home_html='' if is_explore_page else '<div class="footer"><a href="index.html">Return to home</a></div>'
    crumb_html='' if is_explore_page else '<div class="crumb"><a href="index.html">Home</a></div>'
    page_html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(cat['title'])} · NZ Planning System</title>{favicon_links()}<link rel="stylesheet" href="assets/style.css"></head><body><header class="top"><div class="wrap"><div class="inner-header"><a class="brand-logo-link" href="funnel-folly.html" aria-label="Read The Funnel Folly"><img class="brand-logo" src="assets/bosch-funnel-icon.png" alt="Funnel Folly creature — open The Funnel Folly"></a><div class="brand-lockup"><span class="brand-title">NZ PLANNING SYSTEM</span><span class="brand-subtitle">LEGAL KNOWLEDGE BASE</span></div><form class="search inner-search" action="index.html" method="get"><input type="search" name="q" placeholder="Search provisions, concepts, expressions or actors…" aria-label="Search"><button type="submit">Search</button></form><nav class="header-legislation" aria-label="Official legislation"><span class="official-label">Official Legislation:</span><a href="https://www.legislation.govt.nz/act/public/2026/70/en/latest/#LMS1035807" target="_blank" rel="noopener">Planning Act 2026</a><a href="https://www.legislation.govt.nz/act/public/2026/71/en/latest/#LMS1520775" target="_blank" rel="noopener">Natural Environment Act 2026</a></nav></div></div></header><main class="wrap"><div class="layout">{sidebar_html(False)}<section class="main-column"><div class="main-topline">{toggle_html}{crumb_html}</div><h1 class="page-title">{html.escape(cat['title'])}</h1><p>{html.escape(cat['description'])}</p><section class="content-card"><p class="muted small">{len(cat['items'])} matching pages</p>{list_html}</section>{return_home_html}</section></div><nav class="page-jump" aria-label="Page navigation"><a href="#" aria-label="Go to top">↑</a><a href="#page-bottom" aria-label="Go to bottom">↓</a></nav><span id="page-top"></span><span id="page-bottom"></span>{page_script}</main></body></html>'''
    (out/f"{cat['slug']}.html").write_text(page_html,encoding='utf-8')

# Homepage uses the existing Planning Act home page content, without the all-pages list.
def is_home_page(p):
    n=re.sub(r'[^a-z0-9]+',' ',p['title'].casefold()).strip()
    return 'planning act' in n and ('home' in n or 'contents' in n)
home_page=next((p for p in pages.values() if is_home_page(p)),None)
home_tree=''; home_tags=''; home_refs=''
if home_page:
    seen=set(); home_tree=''.join(render_block(bid,seen,'pages/') for bid in children.get(home_page['id'],[]))
    home_tags=''.join(f'<span class="tag">{html.escape(str(t))}</span>' for t in tag_titles(home_page['tags']))
    home_refs=reference_section(home_page['id'],True,is_concept_or_actor(home_page))
root_title=home_page['title'] if home_page else 'NZ Planning System'
index_script=r'''<script>
let records=[];const form=document.getElementById('search-form'),input=document.getElementById('q'),results=document.getElementById('results'),status=document.getElementById('search-status');function selectedView(){return document.body.dataset.actView||selectedActView()}function showHomeContent(show){document.querySelector('#home-welcome')?.toggleAttribute('hidden',!show)}fetch('assets/search-index.json').then(r=>r.json()).then(d=>{records=d;status.textContent="Search the planning system or choose a section from the side panel.";const params=new URLSearchParams(location.search),initial=params.get('q');if(initial){input.value=initial;form.requestSubmit()}}).catch(()=>{status.textContent='Could not load the search index. Please rebuild the site.'});
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function termsFor(q){return q.toLowerCase().trim().split(/\s+/).filter(Boolean)}
function hi(s,q){const terms=termsFor(q).sort((a,b)=>b.length-a.length),lower=s.toLowerCase();let out='',i=0;while(i<s.length){const t=terms.find(t=>lower.startsWith(t,i));if(t){out+='<mark class="search-highlight">'+esc(s.slice(i,i+t.length))+'</mark>';i+=t.length}else{out+=esc(s[i]);i++}}return out}
function isInterp(p){const n=p.title.toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();return n==='npd interpretation'||n==='3 interpretation'||n==='section 3 interpretation'}
function renderGroup(title,items,q,filter=false){let h='<section class="search-group"><h2>'+esc(title)+' <span class="ref-count">'+items.length+'</span></h2>';if(filter)h+='<input class="search-other-filter" type="search" placeholder="Filter other references…" aria-label="Filter other references">';if(!items.length)h+='<p class="muted">No matching references.</p>';else{h+='<div class="search-group-grid">';for(const p of items){const lower=(p.text||'').toLowerCase(),terms=termsFor(q),positions=terms.map(t=>lower.indexOf(t)).filter(i=>i>=0),idx=positions.length?Math.min(...positions):-1;let ex=idx>=0?p.text.slice(Math.max(0,idx-100),Math.min(p.text.length,idx+Math.max(...terms.map(t=>t.length))+220)):p.text.slice(0,220);h+='<article class="search-ref" data-filter-text="'+esc((p.title+' '+ex).toLowerCase())+'"><h3><a href="pages/'+esc(p.slug)+'.html?q='+encodeURIComponent(q)+'&view='+encodeURIComponent(selectedView())+'">'+hi(p.title,q)+'</a></h3><p>'+p.tags.slice(0,4).map(t=>'<span class="tag">'+hi(t,q)+'</span>').join(' ')+'</p><p>'+hi(ex,q)+'</p></article>'}h+='</div>'}return h+'</section>'}
document.getElementById('clear-search')?.addEventListener('click',()=>{input.value='';results.innerHTML='';showHomeContent(true);status.textContent=`Search ${records.length.toLocaleString()} pages.`;input.focus();const url=new URL(location.href);url.searchParams.delete('q');history.replaceState(null,'',url)});form.addEventListener('submit',e=>{e.preventDefault();const q=input.value.trim(),terms=termsFor(q),view=selectedView(),url=new URL(location.href);showHomeContent(!q);if(q)url.searchParams.set('q',q);else url.searchParams.delete('q');url.searchParams.set('view',view);history.replaceState(null,'',url);if(q)saveRecent({title:q,href:'index.html?q='+encodeURIComponent(q)+'&view='+view,type:'search'});results.innerHTML='';if(!q){status.textContent=`Search ${records.length.toLocaleString()} pages.`;return}const hits=records.map(p=>{const title=(p.title||'').toLowerCase(),tags=(p.tags||[]).join(' ').toLowerCase(),hay=(title+' '+(p.name||'')+' '+tags+' '+(p.text||'')).toLowerCase();const score=terms.reduce((n,t)=>n+(title.includes(t)?4:0)+(tags.includes(t)?2:0+0)+(hay.includes(t)?1:0),0);return {...p,score,hay}}).filter(p=>terms.every(t=>p.hay.includes(t))).filter(p=>view==='both'||p.act==='shared'||(view==='pa'&&p.act==='pa')||(view==='nea'&&p.act==='nea')).sort((a,b)=>b.score-a.score||a.title.localeCompare(b.title));status.textContent=`${hits.length} matching pages. All search terms must match; matching terms are highlighted.`;if(!hits.length){results.innerHTML='<div class="empty">No matches found for all terms. Try fewer words or a different spelling.</div>';return}const interp=hits.filter(isInterp),groups={RSP:[],LUP:[],NEP:[]},other=[];for(const p of hits){if(isInterp(p))continue;let placed=false;const pageText=(p.text||'').toLowerCase(),tagSet=new Set((p.tags||[]).map(t=>t.toLowerCase().trim()));const aliases={RSP:['regional spatial plan','regional spatial plans','rsp'],LUP:['land use plan','land use plans','lup'],NEP:['natural environment plan','natural environment plans','nep']};for(const k of Object.keys(groups)){const byTag=tagSet.has(k.toLowerCase())||(p.tags||[]).some(t=>t.toLowerCase().includes(k.toLowerCase()));const normalizedText=' '+pageText.replace(/[^a-z0-9]+/g,' ')+' ';const byText=aliases[k].some(term=>normalizedText.includes(' '+term+' '));if(byTag||byText){groups[k].push(p);placed=true}}if(!placed)other.push(p)}const interpFiltered=interp;results.innerHTML=renderGroup('Interpretation',interpFiltered,q)+'<section class="search-group"><h2>Related instruments</h2><div class="search-group-grid">'+['RSP','LUP','NEP'].map(k=>renderGroup(k,groups[k],q)).join('')+'</div></section>'+renderGroup('Other references',other,q,true);results.querySelectorAll('.search-other-filter').forEach(el=>el.addEventListener('input',()=>{const q2=el.value.toLowerCase();el.parentElement.querySelectorAll('.search-ref').forEach(card=>card.hidden=!card.dataset.filterText.includes(q2))}))});
</script>'''
index_html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NZ Planning System</title>{favicon_links()}<link rel="stylesheet" href="assets/style.css"></head><body><header class="top"><div class="wrap"><div class="inner-header"><a class="brand-logo-link" href="funnel-folly.html" aria-label="Read The Funnel Folly"><img class="brand-logo" src="assets/bosch-funnel-icon.png" alt="Funnel Folly creature — open The Funnel Folly"></a><div class="brand-lockup"><span class="brand-title">NZ PLANNING SYSTEM</span><span class="brand-subtitle">LEGAL KNOWLEDGE BASE</span></div><form class="search inner-search" id="search-form"><input id="q" type="search" placeholder="Search provisions, concepts, expressions or actors…" aria-label="Search"><button type="submit">Search</button><button type="button" id="clear-search">Clear</button></form><nav class="header-legislation" aria-label="Official legislation"><span class="official-label">Official Legislation:</span><a href="https://www.legislation.govt.nz/act/public/2026/70/en/latest/#LMS1035807" target="_blank" rel="noopener">Planning Act 2026</a><a href="https://www.legislation.govt.nz/act/public/2026/71/en/latest/#LMS1520775" target="_blank" rel="noopener">Natural Environment Act 2026</a></nav></div></div></header><main class="wrap"><div class="layout">{sidebar_html(False)}<section class="main-column"><nav class="view-switch home-view-switch" aria-label="Choose legislation view"><a href="?view=pa" data-view="pa">Planning Act</a><a href="?view=nea" data-view="nea">Natural Environment Act</a><a href="?view=both" data-view="both">Both</a></nav><div id="search-status" class="muted small"></div><div id="results"></div><section class="home-welcome" id="home-welcome"><h1>Welcome</h1><p>Welcome to a navigation site of the New Zealand planning system. The Resource Management Act 1991 has been replaced by a two-Act system with a top-down hierarchy of decision-making, touted as ‘the funnel’.</p><figure><img src="assets/planning-system-funnel.jpeg" alt="Diagram of the two-Act planning system hierarchy, showing national instruments, national policy direction, standards and regional and land use plans."><figcaption>The two-Act system and its top-down hierarchy of decision-making.</figcaption></figure></section></section></div><nav class="page-jump" aria-label="Page navigation"><a href="#" aria-label="Go to top" title="Go to top">↑</a><a href="#page-bottom" aria-label="Go to bottom" title="Go to bottom">↓</a></nav><span id="page-top"></span><span id="page-bottom"></span><div class="footer">Generated from your Logseq EDN export · Site built {datetime.now(ZoneInfo('Pacific/Auckland')).strftime('%d %B %Y')}. Verify statutory wording against official legislation.</div></main>{index_script}{page_script}</body></html>'''
(out/'index.html').write_text(index_html,encoding='utf-8')

# Dedicated illustrated essay reached by clicking the funnel logo.

# First-class split reading workspace: each Act is independently navigable and scrollable.
pa_contents=next((p for p in pages.values() if p['title'].casefold()=='planning act 2026 — contents'),None)
nea_contents=next((p for p in pages.values() if p['title'].casefold()=='natural environment act 2026 - contents'),None)
pa_src='pages/'+(pa_contents['slug'] if pa_contents else 'planning-act-2026-contents')+'.html?pane=1'
nea_src='pages/'+(nea_contents['slug'] if nea_contents else 'natural-environment-act-2026-contents')+'.html?pane=1'
act_map=json.dumps(act_pages,ensure_ascii=False)
both_html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Both Acts · NZ Planning System</title><link rel="stylesheet" href="assets/style.css"></head><body><header class="top"><div class="wrap"><div class="inner-header"><a class="brand-logo-link" href="funnel-folly.html" aria-label="Read The Funnel Folly"><img class="brand-logo" src="assets/bosch-funnel-icon.png" alt="Funnel Folly creature — open The Funnel Folly"></a><div class="brand-lockup"><span class="brand-title">NZ PLANNING SYSTEM</span><span class="brand-subtitle">LEGAL KNOWLEDGE BASE</span></div><form class="search inner-search" action="index.html" method="get"><input type="search" name="q" placeholder="Search provisions, concepts, expressions or actors…" aria-label="Search"><button type="submit">Search</button></form><nav class="header-legislation" aria-label="Official legislation"><span class="official-label">Official Legislation:</span><a href="https://www.legislation.govt.nz/act/public/2026/70/en/latest/#LMS1035807" target="_blank" rel="noopener">Planning Act 2026</a><a href="https://www.legislation.govt.nz/act/public/2026/71/en/latest/#LMS1520775" target="_blank" rel="noopener">Natural Environment Act 2026</a></nav></div></div></header><main class="both-panels"><iframe id="left-pane" class="both-pane" title="Planning Act" src="{pa_src}"></iframe><div id="both-divider" class="both-divider" role="separator" aria-orientation="vertical" aria-valuemin="25" aria-valuemax="75" aria-valuenow="50" aria-label="Resize reading panes" tabindex="0"></div><iframe id="right-pane" class="both-pane" title="Natural Environment Act" src="{nea_src}"></iframe></main><script>
const acts={act_map};const frames=[document.getElementById('left-pane'),document.getElementById('right-pane')];
function bindFrame(frame,index){{frame.addEventListener('load',()=>{{try{{const doc=frame.contentDocument;doc.body.classList.add('pane-mode');doc.addEventListener('click',ev=>{{const a=ev.target.closest('a[href]');if(!a)return;const u=new URL(a.href,location.href);const slug=u.pathname.split('/').pop().replace(/\\.html$/,'');const target=acts[slug];if(!target)return;const here=index===0?'pa':'nea';if(target!=='shared'&&target!==here){{ev.preventDefault();u.searchParams.set('pane','1');frames[index===0?1:0].src=u.href;}}}},true);}}catch(e){{}}}})}}frames.forEach(bindFrame);
const divider=document.getElementById('both-divider'),panels=document.querySelector('.both-panels'),splitKey='planning-act-both-split-v1';let drag=false;function setSplit(pct,save=false){{pct=Math.max(25,Math.min(75,pct));frames[0].style.flex='0 0 '+pct+'%';frames[1].style.flex='1 1 auto';divider.setAttribute('aria-valuenow',String(Math.round(pct)));if(save)try{{localStorage.setItem(splitKey,String(pct))}}catch(e){{}}}}try{{const saved=Number(localStorage.getItem(splitKey));if(saved>=25&&saved<=75)setSplit(saved)}}catch(e){{}}divider.addEventListener('pointerdown',e=>{{drag=true;divider.setPointerCapture(e.pointerId)}});divider.addEventListener('pointermove',e=>{{if(!drag)return;const r=panels.getBoundingClientRect(),vertical=window.matchMedia('(max-width:850px)').matches;setSplit((vertical?(e.clientY-r.top)/r.height:(e.clientX-r.left)/r.width)*100)}});divider.addEventListener('pointerup',()=>{{if(drag)setSplit(parseFloat(frames[0].style.flexBasis)||50,true);drag=false}});divider.addEventListener('pointercancel',()=>{{drag=false}});divider.addEventListener('keydown',e=>{{const vertical=window.matchMedia('(max-width:850px)').matches,positive=vertical?'ArrowDown':'ArrowRight',negative=vertical?'ArrowUp':'ArrowLeft';if(e.key===positive||e.key===negative){{e.preventDefault();setSplit(parseFloat(frames[0].style.flexBasis||'50%')+(e.key===positive?3:-3),true)}}}});
</script></body></html>'''
(out/'both.html').write_text(both_html,encoding='utf-8')

essay_html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>The Funnel Folly · NZ Planning System</title>{favicon_links()}<link rel="stylesheet" href="assets/style.css"></head><body class="funnel-folly-page"><header class="top home-top"><div class="wrap"><div class="inner-header"><a class="brand-logo-link" href="index.html" aria-label="NZ Planning System home"><img class="brand-logo" src="assets/bosch-funnel-icon.png" alt="Funnel Folly creature"></a><div class="brand-lockup"><span class="brand-title">NZ PLANNING SYSTEM</span><span class="brand-subtitle">LEGAL KNOWLEDGE BASE</span></div><a class="essay-return" style="margin:0 0 0 auto" href="index.html">Home</a></div></div></header><main class="wrap funnel-essay"><div class="funnel-layout"><aside class="essay-gallery" aria-label="Bosch-inspired funnel illustrations"><div class="essay-track"><figure><img src="assets/funnel-essay/funnel-red-cloak.jpg" alt="Bosch-like figure wearing a funnel-shaped hat and red cloak" loading="lazy"></figure><figure><img src="assets/funnel-essay/funnel-book.jpg" alt="A funnel-hatted figure beside a reader and an open book" loading="lazy"></figure><figure><img src="assets/funnel-essay/funnel-barrel.jpg" alt="A funnel-hatted figure standing on a barrel" loading="lazy"></figure><figure><img src="assets/funnel-essay/funnel-goose.jpg" alt="A strange figure riding a large bird" loading="lazy"></figure><figure><img src="assets/funnel-essay/funnel-butt.jpg" alt="A surreal funnel-like figure with birds" loading="lazy"></figure><figure><img src="assets/funnel-essay/funnel-figure.jpg" alt="A strange Bosch-like figure wearing a tall funnel hat" loading="lazy"></figure><figure><img src="assets/funnel-essay/funnel-red-cloak.jpg" alt="Bosch-like figure wearing a funnel-shaped hat and red cloak" loading="lazy"></figure><figure><img src="assets/funnel-essay/funnel-book.jpg" alt="A funnel-hatted figure beside a reader and an open book" loading="lazy"></figure><figure><img src="assets/funnel-essay/funnel-barrel.jpg" alt="A funnel-hatted figure standing on a barrel" loading="lazy"></figure><figure><img src="assets/funnel-essay/funnel-goose.jpg" alt="A strange figure riding a large bird" loading="lazy"></figure><figure><img src="assets/funnel-essay/funnel-butt.jpg" alt="A surreal funnel-like figure with birds" loading="lazy"></figure><figure><img src="assets/funnel-essay/funnel-figure.jpg" alt="A strange Bosch-like figure wearing a tall funnel hat" loading="lazy"></figure></div></aside><article class="essay-copy"><h1 class="page-title">The Funnel Folly</h1><p>The new planning system in New Zealand is described as a funnel, touting the promise of more centralised decision-making to support fewer needless debates, thereby reducing litigation and process costs. National consistency, delivered via the funnel, is presented as both the answer and the architecture. But to use it as a proxy for certainty and efficiency is a rather big claim.</p><p>'The funnel' has an out-of-zeitgeist, dystopic quality about it. Totally unrelated, but Hieronymus Bosch's funnel-wearing figures share similarly uncanny imaginative connections with this rather dull apparatus. The funnel features across Bosch's works as a curious headpiece, adorning physicians, priests, nuns and other creatures.</p><p>The funnel does not seem to be used as it should. Authoritative figures wearing funnel fascinators, touting empty wisdom. It's all for show; all to deceive the gullible. But over time, body-object, man-funnel... an uncanny being with a life of its own. Those who once deceived become gullible themselves. A tool they formed is now beyond themselves. Those wearing the funnel, falsifying their own authority.</p><p>These strange funnel menageries feel deeply rooted in the silly creatures of medieval imagination. Perhaps our funnel and Bosch's are not entirely unrelated after all, given the planning system's own inheritance of English legal and institutional thinking.</p><p>All to say, no one wants to be an accomplice to this funnel folly. But here we are. Be wary of the stone of madness hardening in your head.</p><figure class="essay-final-image"><img src="assets/funnel-essay/removing-the-stone-detail.jpg" alt="Detail of Bosch's Removing the Stone of Madness" loading="lazy"></figure><a class="essay-return" href="index.html">Return to the NZ Planning System</a><div class="footer">An illustrated diversion from the NZ Planning System.</div></article></div></main></body></html>''' 
(out/'funnel-folly.html').write_text(essay_html,encoding='utf-8')

manifest={'version':'2.1.0','built_at_nz':datetime.now(ZoneInfo('Pacific/Auckland')).isoformat(timespec='seconds'),'source_file':src.name,'datoms_parsed':count,'entities':len(entities),'pages':len(pages),'blocks_with_page':len(block_info),'pages_without_children':sum(not children.get(pid) for pid in pages),'generated_files':len(pages)+len(browse_categories)+5,'home_page':home_page['title'] if home_page else None,'pages_with_linked_references':sum(bool(incoming_linked.get(p['id'])) for p in pages.values()),'pages_with_unlinked_references':sum(bool(unlinked_refs.get(p['id'])) for p in pages.values()),'linked_reference_edges':sum(len(v) for v in incoming_linked.values()),'unlinked_reference_matches':sum(len(v) for v in unlinked_refs.values()),'browse_category_counts':{c['title']:len(c['items']) for c in browse_categories},'prototype_notes':['Version 2.1.0 adds default side-by-side Act comparisons for concept and actor pages.','Page and block titles are extracted from :block/title.','Block ordering uses the exported :block/order value.','UUID links resolve to human-readable page or block titles where available.','Saved and candidate references are merged and sorted numerically by statutory provision, then schedule.','Concept and actor pages group references by interpretation, RSP, LUP, NEP and other references.','Version 4 adds sticky graph navigation, recent pages, provision groups, page-jump controls, improved reference snippets and tag styling.','Unlinked references are candidate page-title matches and may include false positives.']}
(out/'build-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps(manifest,indent=2))
