# Planning Act Knowledge Base — repaired Version 4 package

This package is based on the latest supplied Logseq graph export (`source/graph.edn`) and retains the Version 4 navigation and reference features.

## Fixes in this package

- Corrected search JavaScript so the page can parse and run in Safari.
- Search now treats multiple words as an **AND** query: every term must occur somewhere in a result's title, name, tags, or text. For example, `growth and change` requires all three words to be present. Each term is highlighted in the result excerpt.
- Instrument reference sections for RSP, LUP, and NEP now use full-width stacked cards instead of three narrow columns, making reference titles and context easier to read.
- The prebuilt `site/` includes all generated pages, `assets/style.css`, and `assets/search-index.json`.
- The GitHub Pages workflow rebuilds from `source/graph.edn` and publishes the complete `site/` directory.

## Contents

- `build_site.py` — site generator.
- `source/graph.edn` — graph export used to build this package.
- `site/` — complete prebuilt website, including search index and all generated pages.
- `.github/workflows/deploy-pages.yml` — GitHub Pages deployment workflow.

## Rebuild locally

From the repository root:

```bash
python build_site.py source/graph.edn site
```

Python 3.10+ is recommended. No third-party Python packages are required.

## Publish to GitHub Pages

Commit/push the package contents, including `build_site.py`, `source/graph.edn`, `.github/workflows/deploy-pages.yml`, and the complete `site/` folder. The workflow rebuilds the site and publishes `site/`.

After deployment, confirm that this URL loads JSON rather than a 404:

`https://hshingler.github.io/PlanningAct2026/assets/search-index.json`

If it returns 404, the deployed files/workflow are incomplete or the published base path differs from the URL; browser search cannot work until that is corrected.

## Notes

- Recently visited pages are stored locally in the visitor's browser.
- Search and references are generated from the supplied graph export. Candidate unlinked references can include false positives. Verify statutory wording and legal context against the official legislation.
