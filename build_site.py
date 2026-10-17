#!/usr/bin/env python3
"""Build the static Planning Act viewer directly from a Logseq DB-graph SQLite file.

Uses only Python's standard library. Reads the materialized `kvs` index entries,
decodes Logseq's compact Transit-style values, and reconstructs current entity
attributes by their latest transaction. The EDN export is not used.
"""
import json
import sqlite3
import sys
import shutil
from pathlib import Path
from collections import defaultdict

def transit_decode(value):
    """Decode the subset of Transit JSON used in Logseq's kvs records."""
    cache = []
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_-"

    def cache_index(code):
        n = 0
        for ch in code:
            if ch not in chars:
                return None
            n = n * 44 + chars.index(ch)
        return n

    def decode_tag(s):
        if s.startswith("~u"):
            return {"__uuid__": s[2:]}
        if s.startswith("~i"):
            try:
                return int(s[2:])
            except ValueError:
                return s
        if s.startswith("~:"):
            return s[2:]
        if s.startswith("~$"):
            return s[2:]
        return s

    def walk(v):
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {walk(k): walk(x) for k, x in v.items()}
        if isinstance(v, str):
            if v.startswith("^") and len(v) > 1:
                ix = cache_index(v[1:])
                if ix is not None and ix < len(cache):
                    return decode_tag(cache[ix])
            out = decode_tag(v)
            # Logseq's encoded keyword/symbol strings are cached. UUID/numeric
            # tagged values are not keyword aliases and must not shift indexes.
            if v.startswith("~:") or v.startswith("~$"):
                cache.append(v)
            return out
        return v

    return walk(value)

def norm_value(v):
    if isinstance(v, dict) and "__uuid__" in v:
        return v["__uuid__"]
    return v

def read_sqlite(path):
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(kvs)")}
        if not {"addr", "content"}.issubset(cols):
            raise ValueError("This file does not contain the expected Logseq `kvs` table.")
        # Entries >= 1,000,001 are materialized key/index records. The small
        # address range contains schema and transaction-log records.
        rows = con.execute(
            "SELECT addr, content FROM kvs WHERE addr >= 1000001 ORDER BY addr"
        )
        datoms = set()
        parsed_rows = 0
        for addr, content in rows:
            if not content:
                continue
            try:
                decoded = transit_decode(json.loads(content))
            except Exception as e:
                raise ValueError(f"Could not decode kvs record {addr}: {e}") from e
            if not (isinstance(decoded, list) and len(decoded) >= 3 and decoded[1] == "keys"):
                continue
            parsed_rows += 1
            for d in decoded[2]:
                if not (isinstance(d, list) and len(d) >= 4):
                    continue
                entity, attr, value, tx = d[:4]
                if not isinstance(entity, int) or not isinstance(attr, str) or not isinstance(tx, int):
                    continue
                if attr.startswith("^"):
                    # Unknown compact alias. It is not a core block field.
                    continue
                value = norm_value(value)
                datoms.add((entity, attr, json.dumps(value, ensure_ascii=False, sort_keys=True), tx))
    finally:
        con.close()

    # The index rows include repeated datoms and historical values. Deduplicate
    # first, then use the latest assertion transaction for each entity/attribute.
    decoded_datoms = [(e, a, json.loads(v), tx) for e, a, v, tx in datoms if tx > 0]
    latest_tx = {}
    for e, a, v, tx in decoded_datoms:
        k = (e, a)
        if tx > latest_tx.get(k, 0):
            latest_tx[k] = tx
    current = defaultdict(dict)
    multi = defaultdict(list)
    for e, a, v, tx in decoded_datoms:
        if tx != latest_tx.get((e, a)):
            continue
        if a in ("block/refs", "block/tags"):
            multi[e].append((a, v))
        else:
            current[e][a] = v
    for e, items in multi.items():
        for a, v in items:
            current[e].setdefault(a, [])
            if v not in current[e][a]:
                current[e][a].append(v)
    return current, {"sqliteIndexRowsParsed": parsed_rows, "uniqueDatoms": len(datoms)}

def build(src, out):
    entities, stats = read_sqlite(src)
    pages = []
    for eid, e in entities.items():
        name, title = e.get("block/name"), e.get("block/title")
        if name and title:
            pages.append({
                "id": eid, "label": title, "name": name,
                "uuid": e.get("block/uuid"), "tags": e.get("block/tags", [])
            })
    page_by_id = {p["id"]: p for p in pages}
    page_by_name = {}
    for p in pages:
        page_by_name[str(p["name"]).casefold()] = p
        page_by_name[str(p["label"]).casefold()] = p
        if p.get("uuid"):
            page_by_name[str(p["uuid"]).casefold()] = p

    records = []
    for eid, e in entities.items():
        if "block/title" not in e:
            continue
        page_id = e.get("block/page")
        pg = page_by_id.get(page_id)
        is_page = bool(e.get("block/name"))
        direct_tags = e.get("block/tags", [])
        page_tags = (pg or {}).get("tags", [])
        resolved_refs = []
        for r in e.get("block/refs", []):
            if r in page_by_id:
                resolved_refs.append({"id": r, "label": page_by_id[r]["label"], "kind": "page"})
            elif r in entities and entities[r].get("block/title") is not None:
                ref_entity = entities[r]
                ref_page = page_by_id.get(ref_entity.get("block/page"))
                resolved_refs.append({
                    "id": r, "label": ref_entity.get("block/title"),
                    "page": ref_page["label"] if ref_page else "", "kind": "block"
                })
        # Preserve properties from the database, not just the fields used by
        # the viewer. Reference-valued properties are left as entity IDs.
        properties = {k: v for k, v in e.items() if not k.startswith("block/")}
        records.append({
            "id": eid, "uuid": e.get("block/uuid"), "text": e.get("block/title") or "",
            "name": e.get("block/name"), "kind": "page" if is_page else "block",
            "pageId": page_id if pg else (eid if is_page else None),
            "page": pg["label"] if pg else (e.get("block/title") if is_page else "(unassigned)"),
            "parentId": e.get("block/parent"), "order": str(e.get("block/order") or ""),
            "tags": direct_tags, "pageTags": page_tags,
            "refs": [r["id"] for r in resolved_refs], "resolvedRefs": resolved_refs,
            "properties": properties
        })

    payload = {
        "meta": {
            "source": "Logseq SQLite database (kvs index)",
            "pageCount": len(pages), "recordCount": len(records),
            "titledBlockCount": sum(1 for r in records if str(r["text"]).strip()),
            **stats
        },
        "pages": pages, "records": records
    }
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "data.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    shutil.copyfile(Path(__file__).with_name("index.html"), out / "index.html")
    print(
        f"Built {out}: {len(pages)} pages, {len(records)} titled records; "
        f"{(out / 'data.json').stat().st_size / 1024 / 1024:.1f} MB data.json"
    )
    print(f"Source: SQLite; parsed index rows: {stats['sqliteIndexRowsParsed']}; unique datoms: {stats['uniqueDatoms']}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 build_site.py graph.sqlite output-folder")
        sys.exit(2)
    build(sys.argv[1], sys.argv[2])
