# Planning Act 2026 — lightweight Logseq database viewer

This repository builds a static searchable viewer **directly from a Logseq database-graph SQLite file**. The EDN export is not used by the build.

## Files

- `source/graph.sqlite` — the source database snapshot.
- `build_site.py` — reads the database's materialized `kvs` index and creates the viewer data.
- `index.html` — the browser interface.
- `.github/workflows/publish.yml` — builds and deploys to GitHub Pages when changes are pushed to `main`.

## Publish on GitHub Pages

1. Upload the repository files while preserving the folder structure, including `.github/workflows/publish.yml` and `source/graph.sqlite`.
2. In the GitHub repository, open **Settings → Pages** and set the build/deployment source to **GitHub Actions**.
3. Push to `main` or manually run **Build and publish Planning Act viewer** in the Actions tab.
4. Check the workflow has succeeded before relying on the published site.

## Updating the site when the Logseq graph changes

1. Let Logseq finish saving/syncing, then close the graph (or Logseq) before taking the database snapshot.
2. Replace `source/graph.sqlite` with a fresh, consistent snapshot of the database, keeping the filename exactly `graph.sqlite`.
3. If the database has a non-empty `-wal` file, do not copy just the main `.sqlite` file. Use SQLite's backup facility or close/checkpoint the database first so the snapshot includes recent changes.
4. Commit and push the replacement file to `main`.
5. Check the GitHub Actions run and inspect the site, especially a few pages whose nesting/order you know well.

The SQLite file in this package is a snapshot of the database supplied for this prototype. It will not update itself when your local Logseq graph changes; you replace it when you want to publish a newer snapshot.

## Test locally

Requires Python 3.10+:

```bash
python3 build_site.py source/graph.sqlite site
python3 -m http.server 8000 --directory site
```

Then open `http://localhost:8000`.

## Important limitations

The builder reconstructs the current page/block fields from Logseq's internal `kvs` index. This is a prototype decoder for Logseq's database representation, which may change between Logseq versions. Validate representative pages against Logseq after changing the source database or updating Logseq. Keep your existing published site and a backup of the source database until you are satisfied with the result.
