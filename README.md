# NZ Planning System — Version 2.1.0

This package updates the combined Logseq graph website with a side-by-side Planning Act / Natural Environment Act comparison view and a consistent shared header design.

## Changes in 2.1.0

- Concept and actor pages now open in **Both Acts** mode by default.
- Each concept/actor page presents Planning Act 2026 and Natural Environment Act 2026 material in adjacent, clearly labelled columns.
- Act attribution is determined from the source block's tags, inheriting an Act tag from parent blocks where needed; it is not inferred solely from the page being linked to.
- Shared material is kept in a separate section below the two Act columns rather than being silently assigned to either Act.
- National Policy Direction material is kept in its own clearly labelled section below the Act comparison.
- The Planning Act-only and Natural Environment Act-only view choices remain available. On comparison pages they show the selected Act column while retaining the shared and NPD sections.
- The site header has been standardised across the homepage, knowledge pages, browse pages and the Both Acts page to match the Natural Environment Act contents-page header design. The Funnel Folly page's header design is deliberately preserved.
- The comparison columns stack vertically on narrower screens.
- The underlying combined Logseq graph is unchanged.

## Build locally

Python 3.10+; no third-party packages are required.

```bash
python build_site.py source/graph.edn site
```

The combined Logseq export is stored at `source/graph.edn`. The prebuilt `site/` directory is included.

## Publish to GitHub Pages

Commit and push `build_site.py`, `source/graph.edn`, `brand-assets/`, `.github/workflows/deploy-pages.yml`, and the generated `site/` directory. The workflow builds from `source/graph.edn` and publishes `site/`.

## Important note

This site is a navigation and knowledge tool generated from the supplied Logseq graph. Check statutory wording, amendments, commencement and legal context against the official legislation. Unlinked references are candidate page-title matches and may include false positives.
