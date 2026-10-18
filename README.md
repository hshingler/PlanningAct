# Planning Act SQLite viewer — Update 1 (patch)

This is a code-only update for the working SQLite-based Planning Act viewer. It intentionally does **not** include `source/graph.sqlite` or a workflow file, so it will not overwrite the latest graph snapshot or your working GitHub Actions setup.

## Apply to the existing GitHub repository

1. Download and unzip this patch.
2. In the existing repository, replace the root `index.html` and `build_site.py` with the versions in this folder.
3. Leave `source/graph.sqlite` and `.github/workflows/deploy.yml` (or your currently working workflow) unchanged.
4. Commit and push to `main`; the existing workflow should rebuild and publish the site.
5. Check the Actions build succeeds and test search, block navigation, tag filtering and linked-reference views.

## Changes

- Highlights search terms in navigation results and the selected page/block.
- Keeps search results visible in the navigation while a result is open; selecting a block result opens its page and scrolls to that block.
- Removes the per-block “↗ refs” button and its output.
- Resolves UUID-only text and UUID page links to readable titles where possible.
- Adds linked-reference views for All, RSP, LUP, NEP and NPD. A specialist view includes a reference if the selected tag is on the referenced page or on the referencing block/source page. Results are grouped by tags in expandable groups.
- Page navigation and tag filtering cover graph pages beyond the main `#PA2026` set, including pages tagged on their blocks. All matching pages are listed; the previous 500-page cap is removed.
- Excludes records/pages explicitly marked with `logseq.property/deleted-at` from normal display.
- Keeps SQLite as the source of truth; no EDN file is required.

## Notes

This patch contains the code only. It does not contain the graph database, so your current database snapshot in GitHub remains untouched. The database snapshot available during development did not contain any pages/blocks tagged `RSP`, `LUP`, `NEP` or `NPD`; the specialist views will populate when those tags exist in the SQLite snapshot used by your repository.
