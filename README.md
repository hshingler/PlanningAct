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


## Favicon and home-page visual link

The builder now copies the required icon files from `brand-assets/` into the generated `site/` root on every build, and adds the favicon links to the home page, browse pages, and individual graph pages. This means the assets are not dependent on manually copying files into the generated `site/` folder after a build.

The funnel-butt image is used as the top-left site logo and browser favicon. The separate visual-note section has been removed from the home page. The builder copies the image and icon files into the generated site on every build.

For this repository, the published site base is `https://hshingler.github.io/PlanningAct/`. After deployment, these should resolve:

- `https://hshingler.github.io/PlanningAct/favicon.ico`
- `https://hshingler.github.io/PlanningAct/favicon-32.png`
- `https://hshingler.github.io/PlanningAct/assets/bosch-funnel-icon.png`
- `https://hshingler.github.io/PlanningAct/assets/search-index.json`

Commit and push `build_site.py`, `brand-assets/`, `source/graph.edn`, `.github/workflows/deploy-pages.yml`, and the rest of the package. The workflow rebuilds and publishes `site/` automatically.
