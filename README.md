# Planning Act 2026 web viewer — Version 1.2

This is a **viewer-code update only** for the existing SQLite-based Planning Act 2026 GitHub Pages site. It does not include or replace your SQLite database, generated `data.json`, or GitHub Actions workflow.

## Apply it to the existing repository

1. Download and unzip this package.
2. In the root of your existing `PlanningAct2026` repository, replace **only** `index.html` and `build_site.py` with the two files in this package.
3. Leave `source/graph.sqlite`, the existing generated site data, and `.github/workflows/deploy.yml` untouched.
4. Commit and push the two replaced files to `main`.
5. Check the existing GitHub Actions deployment completes, then test the items below.

The update is deliberately code-only so it does not overwrite the source graph or change your working deployment workflow. The new viewer will use the `data.json` already published with the site; `build_site.py` is for the existing workflow if/when it rebuilds from the SQLite source.

## Version 1.2 changes

- **Multi-word search:** unquoted words are treated as required terms (for example, `growth and change` finds matches containing both “growth” and “change”). Put a phrase in quotes, square brackets, or parentheses to search it as a phrase.
- **Readable reference labels:** resolve UUID-only block/page labels to readable titles wherever the graph contains a matching entity.
- **Possible unlinked references:** add a page-level section that searches for literal mentions of the current page title/name that are not already linked to that page. These are suggestions for review, not automatic graph edits.
- **No “(empty block)” placeholders:** blank blocks do not display a label; any children remain visible.
- **Stable collapse controls:** move collapse controls into a separate row so they do not disrupt the vertical alignment of block text or hierarchy.
- **Expand/collapse all:** add page-level buttons at the top of each page.
- **More Logseq-like linked references:** group incoming references by their source page, with expandable source-page headings and the referencing blocks underneath. Retain the All, RSP, LUP, NEP and NPD filters.
- Keeps the previous search highlighting, selected-result navigation, tag filtering, deleted-record exclusion and block navigation improvements.

## Safe publishing notes

- Keep a copy of the current repository version before replacing files.
- Do not upload the cleaned SQLite file as part of this patch.
- Do not replace your existing GitHub Actions workflow.
- The possible-unlinked-reference section is intentionally read-only; it does not create Logseq links or modify the database.
