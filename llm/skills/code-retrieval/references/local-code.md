# Complete code ranges and callers

For a known symbol, locate its definition and surrounding boundaries with `rg -n`. Read decorators, the complete body, relevant validation, and error handling. A following match is a boundary only when its scope proves it: nested methods and multiline shell bodies require structural inspection. Use `smart-read outline` when text boundaries are ambiguous.

Trace references in the narrowest owning package first, then its callers and tests. Distinguish definitions, imports, aliases, overrides, and unrelated symbols with the same spelling; grep hits alone do not establish symbol identity. Expand the scope only to resolve an actual uncertainty. If static reads cannot establish a dynamic relationship, use a focused test or report the uncertainty rather than claiming complete reference coverage.

If an exact search repeatedly fails, switch to a behavior query. If smart-read returns an incomplete chunk, read the missing ranges with `sed`; do not keep requesting the same context. Preserve qualifications and surrounding sections when applying this method to documents rather than code.

Earlier known-path experiments favored bounded shell reads over smart-read retrieval volume. That is not evidence for every discovery task or non-code source. Actual model-consumed-token experiments and their limits are recorded separately in the repository's `benchmarks/retrieval/` reports.
