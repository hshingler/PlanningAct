# Planning Act Knowledge Base — Version 4

Version 4 of the static site generated from the Logseq database graph EDN export.

## Included

- `build_site.py` — static-site generator.
- `source/graph.edn` — the graph export used to generate this package.
- `site/` — prebuilt site, including all graph pages, browse pages, search index and stylesheet.
- `.github/workflows/deploy-pages.yml` — GitHub Pages deployment workflow.

## Version 4 changes

- Persistent right-side floating controls to jump to the top or bottom of a page.
- A sticky left sidebar with graph search, recently visited pages, graph exploration links, and collapsible provision navigation.
- Interpretation heading shortened to **Interpretation**; its reference filter matches only references whose opening block text starts with the entered term.
- More Logseq-like opening excerpts on reference cards, with long snippets capped to keep the page readable.
- Reference cards and instrument columns use responsive, minimum-width-safe layout rules to avoid the extremely narrow cards seen in the previous version.
- Tags are styled as quiet classification labels rather than button-like orange chips.
- Improved parsing of nested Logseq UUID links so their readable labels are preserved.

## Rebuild locally

From the repository root:

```bash
python build_site.py source/graph.edn site
```

Python 3.10+ is recommended. No third-party Python packages are required.

## GitHub Pages

Commit the `build_site.py`, `source/graph.edn`, `.github/workflows/deploy-pages.yml`, and generated `site/` directory. The workflow rebuilds the site and publishes the generated `site/` directory. Keep the EDN source in `source/`, not inside `site/`.

## Notes

- Recently visited pages are stored locally in the visitor's browser; they are not sent to a server.
- Search and references are generated from the supplied graph export. Candidate unlinked references can include false positives. Verify legal wording and context against the official legislation.
- The provision navigation is collapsible and lists the graph's provision-tagged pages. Where the graph export does not encode Part/Subpart membership as page titles or tags, the generator cannot reliably infer legal group boundaries; those provisions are retained under the expandable **All provisions** group rather than assigned to guessed Parts.
