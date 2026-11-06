# NZ Planning System — Version 9.0

A static, searchable legal knowledge base generated from the combined Logseq graph export supplied on 6 November 2026. The graph includes the Planning Act 2026, Natural Environment Act 2026 and national policy direction material.

## What's new in v9.0

- Combined graph is now the authoritative source at `source/graph.edn`.
- Act-aware page classification uses the graph's `PA2026` and `NEA2026` tags.
- Planning Act, Natural Environment Act and Both view controls.
- A split reading workspace (`both.html`) with independently scrollable Act panes, a draggable divider and cross-Act link routing.
- Sidebar reorganised into Recently Visited, Start Here (Planning Act, Natural Environment Act and National Policy Direction), and Explore (Actors, Concepts and Instruments).
- Header identity updated to **NZ PLANNING SYSTEM / LEGAL KNOWLEDGE BASE**.
- Editorial paper styling with restrained rules, serif typography and muted accent colours.
- Existing search, references, recent history, block expansion, official legislation links and Funnel Folly essay retained.
- Unlinked-reference detection optimised for the larger combined graph.

## Build locally

Python 3.10+; no third-party packages are required.

```bash
python build_site.py source/graph.edn site
```

The build regenerates the static website, search index, browse pages, and split reading workspace. The prebuilt `site/` directory is included.

## Publish to GitHub Pages

Commit and push `build_site.py`, `source/graph.edn`, `brand-assets/`, `.github/workflows/deploy-pages.yml`, and the generated `site/` directory. The existing workflow builds from `source/graph.edn` and publishes `site/`.

After deployment, confirm that this URL loads JSON rather than a 404:

`https://hshingler.github.io/PlanningAct/assets/search-index.json`

## Important note

This site is a navigation and knowledge tool generated from the supplied Logseq graph. It is not a substitute for checking statutory text, amendments, commencement and legal context against the official legislation.
