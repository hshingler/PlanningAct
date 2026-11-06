# NZ Planning System — Version 2.0.1

This package updates the combined Logseq graph website with the requested navigation, header, Act-view and reference-display fixes.

## Changes in 2.0.1

- Fixed Recently Visited on both the homepage and knowledge pages. Page and search entries now render safely in the sidebar.
- Moved the Act view selector into the top of the sidebar, directly below the Home link.
- The Planning Act, Natural Environment Act and Both views now filter search results and Act-specific knowledge-page content using the `PA2026` and `NEA2026` graph tags. Shared and NPD-tagged pages remain available in either Act view.
- The selected view is preserved when changing views, following search results, and navigating to the National Policy Direction contents page.
- Moved the search field to the centre of the header.
- Moved official legislation links to the far right of the header and added the label “Official Legislation:” above them.
- Removed the “All provisions” catch-all group from the sidebar.
- Renamed “Start here” to “Contents”; removed “home page” from the Act link labels.
- Changed the National Policy Direction sidebar link to the National Policy Direction – Contents page.
- Moved page tag details to directly below the page title.
- Ensured unlinked interpretation matches are collected once per source block, rather than once for every occurrence of the target term within that block.

## Build locally

Python 3.10+; no third-party packages are required.

```bash
python build_site.py source/graph.edn site
```

The combined Logseq export is stored at `source/graph.edn`. The prebuilt `site/` directory is included.

## Publish to GitHub Pages

Commit and push `build_site.py`, `source/graph.edn`, `brand-assets/`, `.github/workflows/deploy-pages.yml`, and the generated `site/` directory. The workflow builds from `source/graph.edn` and publishes `site/`.

## Important note

This site is a navigation and knowledge tool generated from the supplied Logseq graph. Check statutory wording, amendments, commencement and legal context against the official legislation.
