# UI engineering setup

The shared skill turns UI work into a repeatable sequence: inspect the product, reuse its components, apply its design contract, then render and correct the result. It is adapted from the supplied UI Agent Toolchain guide. The dotfiles installer owns installation; the guide's standalone installer is not needed.

## Enable the workflow

After closing Claude and Codex sessions, run this from the dotfiles repository:

```bash
bash llm/ai-install.sh --docs-only
```

This refreshes managed global policies and shared skills in `~/.codex`, `~/.codex-work`, `~/.claude` and `~/.claude-work`, preserving model configuration and RTK imports. Review local policy edits before running: these are managed files and are replaced, not merged. Start a new session afterward. The UI rule loads this skill only for application frontend tasks; no browser, component library or third-party skill is installed automatically.

The retrieval-only migration also copies `ui-engineering`, because it refreshes the same global policies and must not leave their UI skill reference missing.

In a frontend repository, use the existing `DESIGN.md`. If the project needs a new contract, copy and customize [the template](../templates/DESIGN.md) only when that file does not exist. Record the actual component paths, tokens and representative screens rather than leaving “inspect repo” placeholders. An existing product's design takes precedence over template defaults.

A normal request is enough:

> Add a searchable task-run history page with filters, row actions, empty state and mobile layout. Follow the repository design system, reuse components, and visually verify desktop and mobile.

## Optional component discovery and browser tools

Reuse the project's installed library and browser/test tooling first. The optional [pick-ui-library skill](https://github.com/emilkowalski/skills) helps select mature libraries when the project has no suitable component. Review its current source and installation instructions before adding it to the intended profiles; it is not bundled or required. The shared skill already carries the component-selection order.

For compatible projects, the [shadcn MCP documentation](https://ui.shadcn.com/docs/mcp) explains registry discovery. The [Playwright MCP documentation](https://github.com/microsoft/playwright-mcp) covers interactive browser automation. Neither replaces the project's component setup or test suite. Configure them before starting a new session, not midway through a UI task.

Merge only missing servers from [the Claude example](claude-mcp.example.json) into the frontend project's `.mcp.json`, or from [the Codex example](codex-config.example.toml) into the chosen `$CODEX_HOME/config.toml` (`~/.codex` for personal, `~/.codex-work` for work). Never overwrite either configuration or register an already available server twice. Examples follow upstream `@latest` recipes; select reviewed package versions for a reproducible deployment. They require Node/npm, network access and browser setup as described upstream; these integrations have not been runtime-tested by the dotfiles checks.

Keep browser sessions on local previews with test data. Inspect third-party components before execution and avoid exposing authenticated production sessions, secrets or private data to untrusted pages or registries.

## Add project-level enforcement

The [Playwright/axe starter](../qa/ui-quality.example.spec.ts) checks horizontal overflow and automated accessibility violations at mobile and desktop sizes, and saves screenshots. Adapt its route, expected states and core interactions to the real app. It needs `@playwright/test`, `@axe-core/playwright` and an installed browser in that project; adopt it through the project's package manager and existing test configuration rather than installing a second test stack.

Run it against a running preview and wire the adapted test into the project's CI if failures must block changes. The bundled file is only a starter: it is not run by the dotfiles smoke test. Inspect its screenshots yourself or through a vision-capable agent; taking them is not visual review. Passing axe is not proof of full accessibility, and neither axe nor an instruction rule can guarantee good aesthetics. Report blocked browser checks explicitly.
