# XML site prototype

This prototype builds the current site UI from the Planning Act and Natural Environment Act XML sources, then overlays the separate `source/ontology.json` annotations.

## Build

```bash
python3 build_xml_site.py
```

The generated preview is written to `site-xml/` and is ignored by Git. To use different XML files or output directory:

```bash
python3 build_xml_site.py --acts path/to/xml-directory --ontology source/ontology.json --output site-xml
```

## View locally

```bash
python3 -m http.server 8000 --directory site-xml
```

Then open <http://localhost:8000/>. Serve the directory over HTTP so the browser can load the generated search index.

The sample ontology records are marked as prototype examples in `source/ontology.json`; replace or remove them before treating the ontology pages and classifications as your own.
