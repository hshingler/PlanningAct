# Planning Act 2026 — lightweight Logseq DB graph viewer

This is an initial working prototype of a static legislative viewer generated from a Logseq **database graph EDN export**. It does not load the Logseq application at runtime. It uses Python's standard library to turn the EDN datoms into JSON and publishes a small static website via GitHub Pages.

## Included

- `source/graph.edn` — the supplied EDN export used to build this prototype. Replace this with a fresh export when you update the graph.
- `build_site.py` — converts Logseq EDN datoms to a compact data file and copies the viewer.
- `index.html` — reader UI with page list, full-text search, nested block display, and reference inspection.
- `.github/workflows/publish.yml` — automatically builds and deploys to GitHub Pages on pushes to `main`.

## Set up in GitHub (one time)

1. Create a **new repository** for the viewer, or use a separate branch/repository from your existing Logseq site. Do not overwrite the current working site while testing.
2. Upload all files and folders in this package, keeping their folder structure, and commit them to the `main` branch.
3. In the repository, open **Settings → Pages** and set the publishing source to **GitHub Actions**.
4. Open **Actions**. The workflow named “Build and publish Planning Act viewer” should run after the push. When it finishes successfully, open the URL shown in the deployment summary.

## Updating the published Act

1. In Logseq, use **Export graph → Export EDN file** to export the current database graph.
2. Replace `source/graph.edn` with the new export (keep the filename exactly `graph.edn`).
3. Commit and push the replacement to GitHub. The workflow regenerates and republishes the site automatically.

You do not need to edit `data.json` manually; it is generated during the workflow.

## Test locally (optional)

```bash
python3 build_site.py source/graph.edn site
cd site
python3 -m http.server 8000
```

Then open `http://localhost:8000`.

## Important prototype limits

- This is an initial prototype, not yet a validated legal publication. Compare key pages against Logseq before making it public.
- It preserves exported block text, parent/child structure, entity IDs, UUIDs, tags and reference relationships in the generated data. The reader currently provides page search, nested content, and page/block reference exploration; it does **not** yet reproduce every Logseq rendering feature, query, embed, property view, or all block-level navigation semantics.
- The data export includes system pages and property entities; the visible page list is filtered to pages tagged `PA2026` plus the home/index pages. Search is similarly scoped.
- The workflow requires the repository's GitHub Pages source to be set to GitHub Actions. Keep the original site until you have verified the new output.
