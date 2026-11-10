# Existing collection adapter

The bundled [design-system.html](../design-system.html) is the Linux collection's approved visual reference. It loads the bundled shared assets. Use an approved lesson from the target collection as the conversion shell and the reference to judge appearance. These conventions are local, not requirements for unrelated projects. The original collection keeps its own asset copies so its existing pages remain standalone.

## Converter

`scripts/convert.py` uses the installed Python `markdown_it` package with CommonMark and tables. It accepts distinct sibling Markdown sources in lesson order and requires a template containing this UI's head, site header, and sidebar. Raw HTML is preserved only with `--trusted-html`; use that option only after inspecting the source's trust.

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

Reuse `assets/lesson.css`, `assets/theme.js`, and `assets/lesson.js`. The shared serif/sans/mono tokens provide system fonts without downloads. The reading face is 17px/1.65; display headings use 38–62px at weight 500. Preserve existing controls, focus styles, sidebar scrolling, and the narrow rail's reopen control.

Light is the default theme. Theme storage access is guarded; validated light/dark query parameters preserve selection on local lesson links when file storage is isolated. Fragment-only and external links remain unchanged. Print uses the light palette; raster colors are not inverted.

Raster figures are capped at 675px with automatic height. The current vector component uses a separate readable canvas in a local scroll container; these measurements are not universal defaults. Reuse its token-aware strokes and fills without copying lesson content. Keep the design reference synchronized when the shared component changes. Diagram tables should not acquire the reference-table search controls.

## Browser checks

```bash
node /path/to/markdown-to-html/scripts/check.mjs /tmp/lesson-preview
```

The checker expects this UI's controls and palette. It checks desktop and 390px layouts, navigation, table filters, themes, storage denial, SVG accessibility references and text bounds, image loading, contrast, overflow, local files/anchors, and no-JavaScript reading. It saves representative screenshots and a browser log in a reported temporary directory. Inspect diagram screenshots as well; a hero screenshot is not a diagram review.

Use an installed Node with built-in `WebSocket` and installed Chromium. The default is Google Chrome on macOS or `chromium` elsewhere; `CHROME_BIN` selects another installed executable. The checker closes the browser it starts. Do not bypass sandbox restrictions if startup fails. It does not establish screen-reader or editor-preview compatibility.
