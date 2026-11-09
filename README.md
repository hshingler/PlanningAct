# NZ Planning System — XML-based site

The site is built from the Planning Act 2026 and Natural Environment Act 2026 XML source files, with a separate ontology overlay. The existing static-site renderer and UI are retained.

## Sources

- `source/legislation/` contains the Act XML files. These provide the statutory wording, structure, metadata, and internal cross-references.
- `source/ontology.json` contains curated concepts, classifications, tags, and links. The current records are explicitly marked as prototype examples and should be replaced with the site's ontology before being treated as authoritative classifications.
- `build_xml_site.py` joins those sources and generates the site. It does not read `source/graph.edn`.

The XML IDs are used to keep provision references stable. During the build, XML and ontology data are converted into a temporary renderer-compatible format; that temporary file is deleted after the static HTML is generated. No EDN file is required as a content source at runtime or deployment.

## Build locally

Python 3.10+; no third-party packages are required.

```bash
python3 build_xml_site.py
```

The generated site is written to `site/`, which is ignored by Git. To choose another output directory:

```bash
python3 build_xml_site.py --acts source/legislation --ontology source/ontology.json --output site-preview
```

## View locally

```bash
python3 -m http.server 8000 --directory site
```

Open <http://localhost:8000/>. Serve the generated directory over HTTP so browser search can load the JSON index.

## Publish to GitHub Pages

Push the XML files, ontology JSON, build script, renderer, brand assets, and workflow to `main`. GitHub Actions builds `site/` from `source/legislation/` and `source/ontology.json`, then publishes it.

## Scope and source fidelity

The XML build supports the site's existing navigation, search, provision pages, cross-references, Act views, comparison layout, and split-screen reader. Complex legal markup such as tables and editorial notes may need more renderer work. Actor and instrument pages depend on ontology records being added. The current ontology sample and National Policy Direction contents entry are demonstrations/placeholders, not substantive source content.

This site is a navigation and knowledge tool. Check statutory wording, amendments, commencement, and legal context against the official legislation.
