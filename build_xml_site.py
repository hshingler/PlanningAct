#!/usr/bin/env python3
"""Build the static site from legislation XML plus ontology JSON.

Usage: python build_xml_site.py --acts source/legislation --ontology source/ontology.json --output site
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NS = uuid.UUID("bc9af344-87ad-44ac-8b6f-9c695c61d652")


def stable_uuid(value: str) -> str:
    return str(uuid.uuid5(NS, value))


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def norm_label(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower())


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:80] or "page"


def xml_inline(el: ET.Element, id_to_page: dict[str, int], id_to_uuid: dict[str, str]) -> str:
    """Convert inline XML to the renderer's lightweight markdown link syntax."""
    out = el.text or ""
    for child in el:
        tag = child.tag
        inner = xml_inline(child, id_to_page, id_to_uuid)
        if tag == "intref":
            target = child.get("href", "")
            if target in id_to_uuid:
                inner = f"[{inner}]([[{id_to_uuid[target]}]])"
        elif tag == "emphasis":
            style = child.get("style", "italic")
            inner = f"**{inner}**" if style == "bold" else f"*{inner}*"
        elif tag == "def-term":
            pass
        elif tag in {"entry", "cell"}:
            inner = " " + inner + " | "
        out += inner
        out += child.tail or ""
    return out


def element_text(el: ET.Element, id_to_page: dict[str, int], id_to_uuid: dict[str, str], depth: int = 0) -> str:
    """Flatten a legal structure while keeping paragraph and table boundaries readable."""
    if el.tag in {"para", "subprov", "label-para", "def-para", "row", "crosshead", "example"}:
        pieces = []
        label = el.find("label")
        marker = clean("".join(label.itertext())) if label is not None else ""
        if marker:
            pieces.append(("\u2003" * depth) + f"({marker})")
        if el.text and el.text.strip():
            pieces.append(el.text.strip(" \t\r\n"))
        for child in el:
            if child.tag == "label":
                continue
            if child.tag in {"para", "subprov", "label-para", "def-para", "row", "crosshead", "example"}:
                child_depth = depth + (1 if child.tag == "label-para" else 0)
                value = element_text(child, id_to_page, id_to_uuid, child_depth)
            else:
                value = xml_inline(child, id_to_page, id_to_uuid)
            if value.strip():
                pieces.append(value.strip(" \t\r\n"))
        if marker and len(pieces) > 1:
            pieces[0] += " " + pieces.pop(1)
        text = "\n".join(pieces)
    else:
        text = xml_inline(el, id_to_page, id_to_uuid)
    return text.strip(" \t\r\n")


class Graph:
    def __init__(self):
        self.next_id = 1
        self.rows: list[tuple[int, str, object]] = []
        self.tag_ids: dict[str, int] = {}

    def entity(self, **attrs):
        eid = self.next_id
        self.next_id += 1
        for attr, values in attrs.items():
            if not isinstance(values, list):
                values = [values]
            for value in values:
                self.rows.append((eid, attr, value))
        return eid

    def tag(self, title: str) -> int:
        if title not in self.tag_ids:
            self.tag_ids[title] = self.entity(**{"block/title": title})
        return self.tag_ids[title]

    def page(self, title: str, key: str, tags=(), refs=(), uid=None):
        eid = self.entity(**{
            "block/name": slug(title), "block/title": title,
            "block/uuid": uid or stable_uuid("page:" + key),
            "block/tags": [self.tag(t) for t in tags],
            "block/refs": list(refs),
        })
        return eid

    def block(self, title: str, page: int, parent: int, order: int, key: str, refs=(), tags=()):
        return self.entity(**{
            "block/title": title, "block/page": page, "block/parent": parent,
            "block/order": f"{order:06d}", "block/uuid": stable_uuid("block:" + key),
            "block/refs": list(refs), "block/tags": [self.tag(t) for t in tags],
        })

    @staticmethod
    def edn(value):
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        return json.dumps(str(value), ensure_ascii=False)

    def write(self, path: Path):
        with path.open("w", encoding="utf-8") as f:
            f.write("{:datoms [\n")
            for eid, attr, value in self.rows:
                f.write(f" [{eid} :{attr} {self.edn(value)}]\n")
            f.write("]}\n")


def read_act(path: Path):
    root = ET.parse(path).getroot()
    title = clean("".join(root.find("./cover/title").itertext()))
    key = "planning-act-2026" if "planning act" in title.lower() else "natural-environment-act-2026"
    act_tag = "PA 2026" if key.startswith("planning") else "NEA 2026"
    return {"path": path, "root": root, "title": title, "key": key, "tag": act_tag}


def section_label(prov: ET.Element) -> str:
    label = clean(prov.findtext("label", ""))
    heading = clean(prov.findtext("heading", "Untitled provision"))
    return f"§{label} — {heading}" if label else heading


def provision_context(root: ET.Element, prov: ET.Element) -> tuple[str, str | None]:
    """Return a unique key and display title, qualifying schedule clauses."""
    parents = {child: parent for parent in root.iter() for child in parent}
    label = clean(prov.findtext("label", ""))
    heading = clean(prov.findtext("heading", "Untitled provision"))
    node = parents.get(prov)
    schedule = None
    while node is not None:
        if node.tag == "schedule":
            schedule = node
            break
        node = parents.get(node)
    if schedule is not None:
        sch_no = clean(schedule.findtext("label", ""))
        sch_title = clean(schedule.findtext("heading", ""))
        key = f"schedule-{sch_no}:{label or 'clause'}:{prov.get('id')}"
        title = f"Schedule {sch_no}, clause {label} — {heading}"
        if sch_title:
            title += f" ({sch_title})"
        return key, title
    return label or prov.get("id", "unknown"), section_label(prov)


def build(acts_dir: Path, ontology_path: Path, output: Path):
    act_files = sorted(acts_dir.glob("*.xml"))
    if not act_files:
        raise SystemExit(f"No XML files found in {acts_dir}")
    acts = [read_act(p) for p in act_files]
    ontology = json.loads(ontology_path.read_text(encoding="utf-8")) if ontology_path.exists() else {"concepts": [], "provisions": {}}
    graph = Graph()

    # Create provision pages first so XML cross-references can resolve to pages.
    by_key = {}
    id_to_page, id_to_uuid, page_meta = {}, {}, {}
    xmlid_to_item = {}
    for act in acts:
        for prov in act["root"].findall(".//prov"):
            xmlid = prov.get("id")
            local_key, title = provision_context(act["root"], prov)
            refkey = f"{act['key']}:{local_key}"
            by_key[refkey] = {"act": act, "prov": prov, "title": title, "xmlid": xmlid}
            xmlid_to_item[xmlid] = by_key[refkey]
            page_meta[refkey] = {"act": act, "prov": prov}
            uid = stable_uuid("xml:" + xmlid)
            id_to_uuid[xmlid] = uid
    # Allocate page entities in a second pass; resolve exact legal IDs thereafter.
    for refkey, item in by_key.items():
        act, prov, title, xmlid = item["act"], item["prov"], item["title"], item["xmlid"]
        extra_tags = ontology.get("provisions", {}).get(refkey, {}).get("tags", [])
        page = graph.page(title, "provision:" + xmlid, [act["tag"], "Provision", *extra_tags], uid=id_to_uuid[xmlid])
        item["page"] = page
        id_to_page[xmlid] = page

    # Build contents pages, preserving the XML's part/subpart hierarchy.
    contents_by_act = {}
    for act in acts:
        page_title = ("Planning Act 2026 — Contents" if act["key"].startswith("planning")
                      else "Natural Environment Act 2026 - Contents")
        page = graph.page(page_title, "contents:" + act["key"], [act["tag"]])
        contents_by_act[act["key"]] = page
        home = page
        root_elems = list(act["root"].find("body"))
        counter = 0

        def add_section_refs(parent_node, children):
            nonlocal counter
            for child in children:
                if child.tag == "prov":
                    xmlid = child.get("id")
                    item = xmlid_to_item.get(xmlid)
                    if item:
                        counter += 1
                        graph.block(f"[{item['title']}]([[{id_to_uuid[xmlid]}]])", home, parent_node, counter,
                                    f"toc:{act['key']}:{xmlid}", refs=[item["page"]], tags=[act["tag"]])
                elif child.tag in {"part", "subpart", "schedule", "schedule.group", "schedule.provisions"}:
                    label = clean(child.findtext("label", ""))
                    heading = clean(child.findtext("heading", ""))
                    if child.tag == "schedule":
                        title = f"Schedule {label} — {heading}".strip(" —")
                    elif child.tag == "schedule.provisions":
                        title = "Provisions"
                    elif child.tag == "schedule.group":
                        title = heading or "Schedules"
                    else:
                        title = f"{child.tag.title()} {label} — {heading}".strip(" —")
                    counter += 1
                    node = graph.block(title, home, parent_node, counter, f"toc:{act['key']}:{child.get('id')}", tags=[act["tag"]])
                    add_section_refs(node, list(child))
        add_section_refs(home, root_elems)
        schedule_group = act["root"].find("schedule.group")
        if schedule_group is not None:
            add_section_refs(home, [schedule_group])

    # Render each XML provision into nested, collapsible text blocks.
    for refkey, item in by_key.items():
        act, prov, page = item["act"], item["prov"], item["page"]
        prov_body = prov.find("prov.body")
        if prov_body is None:
            continue
        order = 0
        for child in prov_body:
            if child.tag in {"label", "heading"}:
                continue
            value = element_text(child, id_to_page, id_to_uuid)
            if not value:
                continue
            targets = {id_to_page[e.get("href")] for e in child.iter("intref") if e.get("href") in id_to_page}
            order += 1
            graph.block(value, page, page, order, f"body:{item['xmlid']}:{order}", refs=sorted(targets))

    # Ontology pages and tagged provision overlays are separate from legal source text.
    for concept in ontology.get("concepts", []):
        title = concept["title"]
        page = graph.page(title, "concept:" + concept["id"], ["Concept", *concept.get("tags", [])])
        refs = []
        links = []
        for link in concept.get("links", []):
            target = by_key.get(link["target"])
            if not target:
                raise SystemExit(f"Ontology link from {concept['id']} has unknown target {link['target']}")
            refs.append(target["page"])
            links.append(f"{link.get('relation', 'related to')}: [{target['title']}]([[{id_to_uuid[target['xmlid']]}]])")
        description = concept.get("description", "")
        graph.block(description or title, page, page, 1, "concept-description:" + concept["id"])
        for i, text in enumerate(links, 1):
            target_key = concept["links"][i - 1]["target"]
            target_act = by_key[target_key]["act"]["tag"]
            graph.block(text, page, page, i + 1, f"concept-link:{concept['id']}:{i}", refs=[refs[i - 1]], tags=[target_act])

    # The existing renderer has a fixed NPD navigation link; provide a transparent placeholder.
    graph.page("Illustrative National Policy Direction Contents", "npd-placeholder", ["NPD"])

    with tempfile.TemporaryDirectory(prefix="xml-site-build-") as td:
        edn_path = Path(td) / "xml-derived.edn"
        graph.write(edn_path)
        command = [sys.executable, str(ROOT / "build_site.py"), str(edn_path), str(output)]
        subprocess.run(command, cwd=ROOT, check=True)

    # Keep the shared renderer's UI while correcting its source-specific footer
    # and ensuring the compact preview viewport does not overlap the header.
    css_path = output / "assets/style.css"
    with css_path.open("a", encoding="utf-8") as css:
        css.write("\n@media(max-width:900px){.top .wrap{height:auto;min-height:100px}.inner-header{height:auto;min-height:0;padding:8px 0}}\n")
    for html_path in output.rglob("*.html"):
        source = html_path.read_text(encoding="utf-8")
        source = source.replace("Generated from the supplied Logseq EDN export", "Generated from legislation XML and ontology data")
        source = source.replace("Generated from your Logseq EDN export", "Generated from legislation XML and ontology data")
        html_path.write_text(source, encoding="utf-8")

    # Search is over display text, so remove the renderer's intermediate
    # Logseq-style link notation from indexed XML citations.
    search_path = output / "assets/search-index.json"
    records = json.loads(search_path.read_text(encoding="utf-8"))
    for record in records:
        text = record.get("text", "")
        text = re.sub(r"\[([^\[\]]+)\]\(\[\[[0-9a-fA-F-]{36}\]\]\)", r"\1", text)
        record["text"] = re.sub(r"\[\[([0-9a-fA-F-]{36})\]\]", "", text)
    search_path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")

    manifest_path = output / "build-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({
        "source_mode": "xml-plus-ontology",
        "source_file": [a["path"].name for a in acts],
        "acts": [{"title": a["title"], "file": a["path"].name,
                  "as_at": a["root"].get("date.as.at"), "first_valid": a["root"].get("date.first.valid")} for a in acts],
        "xml_provisions": len(by_key),
        "ontology_concepts": len(ontology.get("concepts", [])),
        "ontology_provision_records": len(ontology.get("provisions", {})),
        "prototype_notes": ["Legal text and provision hierarchy are parsed from Act XML.",
                            "Ontology labels and links are loaded separately from source/ontology.json.",
                            "The existing static site renderer and CSS provide the UI; the preview does not depend on Logseq."],
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(output.resolve()), "provisions": len(by_key),
                      "concepts": len(ontology.get("concepts", [])), "pages": manifest["pages"]}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acts", type=Path, default=ROOT / "source/legislation")
    parser.add_argument("--ontology", type=Path, default=ROOT / "source/ontology.json")
    parser.add_argument("--output", type=Path, default=ROOT / "site")
    args = parser.parse_args()
    build(args.acts, args.ontology, args.output)


if __name__ == "__main__":
    main()
