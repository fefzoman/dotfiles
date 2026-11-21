---
name: ui-engineering
description: Apply library-first UI/UX design, new components, changed interactions or responsive layouts, and UI reviews. Skip for small copy/style edits that only reuse existing UI patterns.
---

# UI Engineering: reuse before inventing

The objective is coherent, accessible production UI without hand-rolling controls or inventing a new visual style each task. Prefer changes that fit the current product over visually exciting but inconsistent additions.

For new applications without an established stack or an explicit user preference, default to **React + Tailwind + shadcn/ui**. Add Sonner, Vaul, cmdk and NumberFlow only where their interactions are useful; do not install every specialist by default. Existing applications keep their established stack and design system.

Use this for application UI, not document conversion covered by `md-to-html`. Resolve bundled paths relative to this skill's directory. The [setup guide](references/setup.md) covers optional tools; do not install or reconfigure them during an unrelated UI task.

## 1. Inspect before modifying

- Detect framework, styling system, package manager, component libraries, design tokens, and reusable components. Read `package.json`, `components.json` if present, `DESIGN.md` if present, and 2-3 representative screens/components.
- Never replace an established component framework, switch between Radix/Base UI, or add competing UI systems unless the user explicitly requests a migration.
- Determine **one primary user goal** per view, its key actions, information density, and required UI states.
- Consult the bundled [pick-ui-library skill](references/pick-ui-library/SKILL.md) only if the existing stack lacks a suitable component and a library choice is needed. Its recommendations do not override the React + shadcn/ui default or justify switching a project's primitive foundation.

## 2. Design before writing code

- For an existing app, follow its system. For a new app, follow `DESIGN.md` or establish a simple coherent direction first.
- If a project design contract is requested and absent, adapt [templates/DESIGN.md](templates/DESIGN.md); never overwrite an existing contract or treat its defaults as a reason to restyle an app.
- Define (briefly, without lengthy design essays): hierarchy, layout/grid, type scale, semantic colors, spacing scale, radius/elevation, breakpoint behavior, and state handling.
- Use existing UI components and CSS/Tailwind semantic tokens. Do not scatter ad hoc hex colors, random radii, arbitrary shadows, or unexplained spacing values across the feature.
- Build a deliberate information hierarchy: page title / context, clear primary action, grouped supporting controls, readable data density, consistent alignment.
- Keep one visual standout per page at most. Do not default to big gradients, glassmorphism, neon glows, noisy animations, huge rounded cards, or repetitive tile dashboards.

## 3. Component selection — prefer this order

1. Reuse an existing project component and its variants.
2. Use the project's installed accessible primitive / UI library.
3. For new applications, default to React + Tailwind + shadcn/ui unless the user or project specifies otherwise. Use shadcn/ui components with one consistent underlying primitive approach and the shadcn MCP for compatible registry discovery where connected. Install only within the task's authorization; inspect third-party code, license and dependencies first.
4. Use specialists for mature interactions when needed: Sonner (toasts), Vaul (mobile drawers), cmdk (command menu), NumberFlow (animated numbers). Verify current packages/APIs before importing.
5. Reuse selectively from trusted designed-component libraries for a distinctive section; check license, accessibility, bundle impact, maintainability and dependency requirements.
6. Hand-roll a control **only** if no suitable existing component can fulfill the requirement; explain why briefly.

Never make fake select boxes, dialogs, popovers, menus, comboboxes or switches from generic clickable divs when accessible primitives are available. Favor semantic HTML, correct labeling, focus handling and keyboard navigation.

## 4. Implementation contract

- Implement responsive behavior intentionally, not by blindly shrinking desktop UI. For dense tables use appropriate scrolling/column priority rather than illegible wrapping.
- Include relevant loading, empty, error, disabled, validation, and success states. Include long/realistic labels and large/empty datasets in checks when applicable.
- Use the product's typography and spacing scales consistently; accessible contrast is more important than fashionable low-contrast text.
- Keep animations purposeful, subtle, reduced-motion aware; repeated high-frequency actions should not be artificially delayed.
- Keep the diff scoped. Do not rewrite a whole design system for a single screen unless asked.

## 5. Render, inspect, correct

Where you can run the app and have Playwright/browser access:

1. Start or identify the preview server. Navigate to the actual changed route.
2. Inspect accessibility snapshot and browser/console errors.
3. Take and **visually examine** screenshots around 375x800 mobile and 1440x900 desktop. Check horizontal overflow, alignment, readable hierarchy, spacing rhythm, clipping, keyboard focus and errors.
4. Critique actual rendered pixels (not just JSX). Fix issues and rerun the check. Aim for at least one meaningful iteration if problems are observed.
5. Exercise core interactions; test keyboard navigation and focus. Run existing tests/build and automated axe checks if configured.

For projects adopting automated checks, adapt the bundled [Playwright/axe starter](qa/ui-quality.example.spec.ts) to the actual route and interactions. It requires project-local dependencies and browser setup; copying it alone does not enable checks or CI. Do not run destructive interactions against production data.

If browser access, dependencies, app credentials or screenshots are unavailable, report the exact limitation and do not claim visual verification.

## 6. Final response

Briefly report:
- Components reused/new dependencies added (and why).
- Design system/tokens applied.
- Screens/states/viewport(s) actually checked and any resulting fixes.
- Tests/accessibility results and remaining unverified items.

Do not present a screenshot-free 'looks great' claim as a verified outcome.
