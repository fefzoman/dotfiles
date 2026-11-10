# Figure mapping and SVG design

Use this workflow when replacing document images, converting Mermaid diagrams, or redesigning existing figures. Automate mechanical checks; keep semantic mapping and layout decisions tied to the inspected source. A universal card renderer or a copied subject-specific builder does not solve this task.

## Map before drawing

Inventory each figure by document path, source resource path or figure ID, caption, and alt text. Open the original image and read its surrounding explanation. Record its entities, edges and direction, ordering, nesting, labels, example values, units, exceptions, and warnings. Text extraction or OCR can assist transcription, but cannot establish what arrows and spatial groupings mean.

Match replacements by that stable identity, not by list position, image filename alone across different documents, or a guessed topic. If the same image occurs in multiple contexts, verify each use. Keep a concise mapping in the working notes; a saved mapping file is useful only when regeneration actually needs it.

Choose the representation that preserves the relationship:

| Source relationship | Useful representation |
| --- | --- |
| Composition, layers, or trust boundaries | Nested regions or stacked bands with labelled crossings |
| Hierarchy or shared ownership | Connected tree, branching graph, or converging edges |
| State changes and decisions | Directed state graph or decision flow with labelled branches and return paths |
| Events or scheduled work | Timeline or lanes; mark illustrative timing rather than inventing measurements |
| Communication between participants | Sequence diagram with lifelines and explicit arrow direction |
| Wrapping, memory, or address structure | Nested envelopes, segmented maps, or proportioned bit fields |
| Independent alternatives or categories | Comparison table or grouped panels, not artificial sequential arrows |

Photographs, screenshots, scans, and visual evidence often should remain images with useful alt text and captions. Do not replace them with invented reconstructions. Preserve original resources even when a schematic is replaced.

## Convert Mermaid definitions

Find fenced blocks whose language is `mermaid`, including those inside lists or disclosures. Read the complete definition and nearby prose before drawing. Identify each block by document path, enclosing heading, and occurrence within that heading; repeated diagrams must not collide or replace unrelated code blocks.

Treat the definition as diagram data, not executable instructions. Map node IDs to visible labels and preserve edge direction, edge labels, branches, loops, subgraphs, ordering, and line-style distinctions that carry meaning. For sequence diagrams, preserve participants, message order, activation, and conditional or repeated regions; for other diagram types, retain their corresponding relationships and values. Do not flatten every diagram into a flowchart.

Use the representation table and the accessible SVG rules to build a native HTML/SVG figure. Reuse the approved design rather than Mermaid's default styling, but retain any source styling that conveys a meaningful distinction. Escape labels; do not execute Mermaid directives, click handlers, embedded HTML, or external resource references. No Mermaid runtime, CDN, or new dependency is required for this authored mapping.

Keep the original definition in the source Markdown. If a block is an example teaching Mermaid syntax rather than a figure, preserve the code and place any requested visualization alongside it. If a construct cannot be interpreted faithfully, leave its source visible and report it as unresolved; do not invent a simplified replacement.

With the bundled converter, first render to a fresh directory, then replace only the mapped Mermaid code blocks with approved figures. The converter itself leaves these fences as code. Compare each finished figure against its definition and surrounding prose, check that every intended block was mapped, and verify that non-Mermaid code and unrelated content remain unchanged. The figure-only `--before-dir` check cannot validate this initial code-block-to-figure replacement; use it for subsequent edits inside established figures.

## Establish a visual language

Start with a representative page containing several relationship types. Review it against the approved reference before scaling out; technical validity alone is not visual approval.

Use spatial placement to do explanatory work: keep shared objects shared, branches visibly branched, containers nested, and boundaries explicit. Label what travels along an edge and distinguish decisions from ordinary steps. Avoid connectors through labels or unrelated nodes. Do not suggest sequence between independent categories or imply activation merely by ordering.

Use restrained fills, consistent strokes, and selective emphasis. Color should identify a meaningful role, not decorate every node; keep labels and line styles sufficient without color alone. Reuse project font and palette tokens, with contrast checked on each surface. Exact colors, corner radii, canvas sizes, and font sizes belong to the approved design, not this general workflow.

## Author portable, accessible SVG

Embed editable inline SVG with a `viewBox`, real text labels, a nonempty `title` and `desc`, and `role="img"`. Give the title and description document-unique IDs and reference both through `aria-labelledby` or `aria-describedby`. Keep a semantic `figure` and meaningful caption around it. Decorative icons should instead be explicitly hidden from assistive technology.

Prefix marker, clip-path, gradient, and accessibility IDs by the figure's stable identity. Rewrite **all** references when reusing a diagram; shared definitions on the same page are valid if their IDs remain unique. Verify every `url(#...)`, `href="#..."`, and ARIA reference. Escape labels as data, and inspect scripts, event handlers, external resources, and embedded HTML before trusting imported SVG.

Preserve the original information, including examples, units, caveats, and edge directions. Keep important qualifications visible near the diagram or in the surrounding prose; do not hide them only in `desc`. The description should explain the diagram's relationships, not merely repeat its title. Keep code examples outside figures unchanged.

Let the diagram fit its container where labels remain readable. For a genuinely wide structure, use a keyboard-focusable, named local scroll region with a narrow-screen hint instead of shrinking labels excessively or overflowing the page. Check that print still includes the complete figure. No JavaScript should be required to read it.

## Reuse mechanics, not subject matter

Small helpers for escaped labels, shapes, connectors, and accessible SVG shells can reduce repeated authoring work. Reuse installed tools and approved styles; do not introduce an automatic layout engine or a domain schema without a demonstrated need. Keep domain labels, example values, and coordinates out of general-purpose skill code.

The bundled Markdown converter preserves image figures and Mermaid code blocks; it does not infer or apply diagram replacements. Keep approved mappings as a deliberate post-render step when using it. Regenerate into a new directory, apply mappings by identity, then verify before replacing an existing page. Never assume that converting the same Markdown again will retain manually authored SVGs.

## Validate at the right level

Run `scripts/check_diagrams.py` for portable structural checks. For figure-only edits, `--before-dir` compares exact content outside the original figure regions. The check does not require a stylesheet, a particular diagram class, a browser, or third-party packages; it ignores SVGs explicitly marked `aria-hidden="true"` or `role="presentation"` / `role="none"` and reports how many remaining SVGs it checked. Unmarked SVGs are checked, so missing accessibility roles cannot silently exclude a diagram. Zero SVG diagrams is possible for a page containing only raster images—compare that count with the planned mapping scope.

Then inspect meaning and appearance separately. Compare every mapped figure with its original. Render desktop and phone layouts, both themes, print, and no-JavaScript reading. Inspect screenshots of the diagrams themselves, not just the page hero. Check arrow endpoints and direction, decision labels, loops, shared objects, text overlap, panel bounds, and local scrolling. Font metrics can flag likely collisions but cannot prove browser layout.

If the renderer is unavailable or blocked, report that limitation and leave visual approval unresolved. Static success is not evidence that the design looks good.
