# Planning Act Knowledge Base — prototype

This is an initial static-site prototype built from the supplied Logseq EDN export.

## What is included
- `site/`: generated static website, including the homepage, browser-side search index, and one HTML page for each exported Logseq page.
- `build.py`: repeatable generator. It reads the EDN file and writes a separate output directory; it does not modify the source export or SQLite database.
- `site/build-manifest.json`: basic extraction counts and caveats.

## Preview locally
Open `site/index.html` in a browser. For browser search to load consistently, serve the `site` folder with a local static server, for example:

```bash
cd site
python3 -m http.server 8000
```

Then visit `http://localhost:8000`.

## Rebuild from the EDN export

```bash
python3 build.py "/path/to/your-export.edn" site
```

## Important limitations
- This is a prototype, not a validated legal publication.
- It extracts page and block titles and uses exported parent/page/order relationships to render content.
- It resolves UUID references when they point to an exported page or block. Some Logseq link forms or references may need further handling.
- Page categories for RSP, LUP, NEP, concepts, expressions and actors have not been editorially assigned. The generator deliberately does not infer legal significance from keyword matches.
- The initial parser should be tested against representative sections, schedules, tags, properties and cross-references before public release.
- No source database or export is included in this package; use your local source file to rebuild.
