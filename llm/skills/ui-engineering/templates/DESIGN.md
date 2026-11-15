# Project UI Design Contract

> Customize this once per project. Existing product tokens and components supersede these defaults. Agents: inspect implementation first; do not change styles globally without a request.

## Product experience

- Default mode for greenfield tools: quiet, professional, information-first interface with compact-but-readable density.
- Optimize for efficient, repeated tasks (filters, status inspection, tables, searching) rather than marketing-style decoration.
- Each screen has one unmistakable primary goal/action and a consistent content hierarchy.
- Avoid the stereotypical AI look: gradients everywhere, random icon tiles, excessive glow, gratuitous animations, over-rounded cards.

## Semantic design system

- **Primary surface:** cool/neutral off-white in light mode, restrained charcoal in dark mode; use existing semantic tokens where present.
- **Accent:** one consistent accent hue, e.g., deep teal in a new project; reserve saturated accents for actions and selected states.
- **Typography:** use the existing app font; otherwise a readable system sans, modest type scale, high contrast and differentiated weight. Avoid adding a new display font without a real product direction.
- **Spacing:** use a consistent 4px-based spacing scale with 8px as common grouping unit; not arbitrary pixel values per component.
- **Radius:** default moderate (6–10px for controls/cards), consistent across similar elements, not randomly mixed.
- **Depth:** choose either borders/surface contrast or subtle shadows. Avoid layered heavy shadows everywhere.
- **Iconography:** one consistent icon family, icons only where they clarify meaning.
- **Motion:** only for useful feedback, respect `prefers-reduced-motion`; one standout per page maximum.
- **Accessibility:** target WCAG AA contrast and keyboard navigability; don't convey state only through color.

## Component policy

1. Existing component library is the source of truth.
2. For new applications without an established stack or explicit user preference, default to React + Tailwind + shadcn/ui, customized with app tokens; use a single consistent underlying primitive stack.
3. Use Sonner for toasts, Vaul for mobile drawers, cmdk for command menus and NumberFlow for animated numbers where useful; do not install all by default.
4. Designed-library components are optional accents; review license and code quality before importing.
5. No homemade accessible primitives if a mature equivalent exists.

## Content & behavior

- Screens must cover loading, empty, error, success/disabled states appropriate to their functionality.
- Data screens: visible sorting/filtering semantics, consistent number/date formatting, dense yet readable tables, clear action placement.
- Mobile: prioritize essential fields and interactions; do not squeeze wide tables beyond readability.
- Forms: labels, help, validation, error recovery, clear success state, predictable keyboard order.

## Site-specific decisions (fill these in)

- Framework and UI primitives: **inspect repo**
- Canonical components directory: **inspect repo**
- Design tokens / global CSS paths: **inspect repo**
- Preferred icon library: **inspect repo**
- Page layout shells: **inspect repo**
- Representative screens to copy: **choose 2–3**
- Required supported viewports: 375px mobile and 1440px desktop unless app requirements differ
