# Planning Act Knowledge Base — version 3 prototype

This package builds a static website from a Logseq database EDN export and publishes it to GitHub Pages. It preserves the EDN source as input and generates HTML, CSS, and a searchable JSON index.

## Version 3 changes

- **Human-readable graph links:** internal page and block links use their titles instead of exposing UUIDs or database IDs where the export provides a title. Tag IDs are resolved to readable labels where possible.
- **Merged references:** saved linked references and candidate unlinked references appear together in one reference list, with duplicate source-block entries removed.
- **Statutory ordering:** references are sorted numerically by section (1, 2, 3 … 9, 10, 11), followed by schedules in numeric order, then other pages.
- **Cleaner homepage:** the homepage uses the existing Logseq page **Planning Act 2026 — Home** and no longer displays the long “All pages” list or the yellow prototype notice.
- **Block controls:** each parent block has an expand/collapse control positioned outside the text flow, plus page-level “Expand all blocks” and “Collapse all blocks” buttons. These controls do not change the text indentation.
- **Concept and actor pages:** references are grouped into an interpretation box (references from §3 — Interpretation and NPD Interpretation), three side-by-side instrument boxes (RSP, LUP, NEP), and a filtered “Other references” box.
- **Grouped search:** searches return references in the same interpretation / RSP / LUP / NEP / other grouping structure. Matching text is highlighted yellow, including after opening a search result.
- **Filtering:** reference lists can be filtered by page title or reference excerpt.

## Source file

Keep your EDN export at:

```text
source/graph.edn
```

Do not put the EDN file inside `site/`. The `site/` folder is generated output and can be replaced on each build. Keep your SQLite database as a separate backup if you wish; this build reads the EDN export.

## Build locally

From the repository root:

```bash
python build_site.py source/graph.edn site
```

The script uses only Python's standard library. It reads the EDN file and regenerates `site/` without modifying the EDN export or SQLite database.

To preview locally:

```bash
python -m http.server 8000 --directory site
```

Then open `http://localhost:8000`.

## GitHub Pages

The included workflow `.github/workflows/deploy-pages.yml` builds from `source/graph.edn` and publishes `site/` using GitHub Actions. In the repository's **Settings → Pages**, set the deployment source to **GitHub Actions**.

Replace or remove any older workflow that runs `python build_site.py source/graph.sqlite site`; do not leave both the old SQLite workflow and this EDN workflow active.

## Important limitations

- Saved linked references come from the relationships stored in the Logseq export.
- Unlinked references are candidate page-title matches in block text. They are useful for discovery, not proof of a legal or conceptual relationship, and may include false positives.
- RSP/LUP/NEP grouping relies on existing graph tags. It is not a complete legal classification or an independent legal conclusion.
- The site is a research prototype, not a validated legal publication. Confirm statutory wording and context against official legislation.
