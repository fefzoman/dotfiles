# Existing collection adapter

The bundled [design-system.html](../assets/design-system.html) is the shared visual reference. It loads the same assets required by every implementation of this skill. The adapter retains the Linux collection's shell conventions; adapt its branding for another collection without recreating the shared theme. Each output bundle keeps local copies of the shared assets so its pages remain standalone.

## Converter

`scripts/convert.py` uses the installed Python `markdown_it` package with CommonMark and tables. It accepts distinct sibling Markdown sources in lesson order and requires a template containing this UI's head, site header, and sidebar. Prepare that template in a staging directory with an `assets/` subdirectory containing the skill's `design-system.css`, `theme.js`, and `design-system.js`. Use the reference shell with its head paths rebased to `assets/`, or update an approved lesson shell to load those files. The converter copies the assets referenced by the template; it does not select a theme itself. Raw HTML is preserved only with `--trusted-html`; use that option only after inspecting the source's trust.

```bash
python3 /path/to/markdown-to-html/scripts/convert.py \
  --template 01-linux-overview.html \
  --output-dir /tmp/lesson-preview \
  --trusted-html \
  md/01-linux-overview.md md/02-filesystems.md
```

It preserves source titles and paragraphs, checks code preservation, rewrites links among included sources, copies referenced local assets, and rejects an existing destination. Resources may not escape their source directory, including through symlinks. Bring intentionally shared assets into the source bundle before conversion. Pass all linked lessons for a full collection.

The shell supplies shared assets and controls, not article enrichments. The converter retains raster image figures and renders Mermaid fences as code; apply approved image and Mermaid mappings after rendering, following [the mapping workflow](diagram-mapping.md). Mermaid conversion is an authored native HTML/SVG step, not an automatic feature of this adapter. Review the fresh output before replacing edited pages. Converter regression tests require the already-installed `markdown_it`; the portable diagram checker does not.

## Local visual conventions

Reuse `assets/design-system.css`, `assets/theme.js`, and `assets/design-system.js` in every output page, including when using another converter. The shared serif/sans/mono tokens provide system fonts without downloads. The reading face is 17px/1.65; display headings use 38–62px at weight 500. Preserve existing controls, focus styles, sidebar scrolling, and the narrow rail's reopen control.

Light is the default theme. Theme storage access is guarded; validated light/dark query parameters preserve selection on local lesson links when file storage is isolated. Fragment-only and external links remain unchanged. Print uses the light palette; raster colors are not inverted.

Raster figures are capped at 675px with automatic height. The current vector component uses a separate readable canvas in a local scroll container; these measurements are not universal defaults. Reuse its token-aware strokes and fills without copying lesson content. Keep the design reference synchronized when the shared component changes. Diagram tables should not acquire the reference-table search controls.

## Browser checks

```bash
node /path/to/markdown-to-html/scripts/check.mjs /tmp/lesson-preview
```

The checker expects this UI's controls and palette. It checks desktop and 390px layouts, navigation, table filters, themes, storage denial, SVG accessibility references and text bounds, image loading, contrast, overflow, local files/anchors, and no-JavaScript reading. It saves representative screenshots and a browser log in a reported temporary directory. Inspect diagram screenshots as well; a hero screenshot is not a diagram review.

Use an installed Node with built-in `WebSocket` and installed Chromium. The default is Google Chrome on macOS or `chromium` elsewhere; `CHROME_BIN` selects another installed executable. The checker closes the browser it starts. Do not bypass sandbox restrictions if startup fails. It does not establish screen-reader or editor-preview compatibility.
