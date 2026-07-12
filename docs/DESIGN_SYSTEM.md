# Kwalitec Library — Design System

This document is the permanent UI guide for Kwalitec Library.

Every current and future page should inherit this system rather than inventing new styles.

**Source of truth**

| Layer | File |
|-------|------|
| Tokens + primitives | `static/design-system.css` |
| Page / feature styles | `static/style.css` |
| Empty state partial | `templates/components/empty_state.html` |
| Status / wild badges | `templates/components/status_chip.html`, `wild_badge.html` |

Load order (see `templates/base.html`):

1. `design-system.css`
2. `style.css`

---

## Design philosophy

Calm. Elegant. Consistent. Information-first.

Think: Things 3, Linear, Apple Books, Notion, Craft.

Prefer:

- Shared tokens over hard-coded values
- Reusable classes (`.btn`, `.ds-card`, `.badge`, `.empty-state`) over one-off CSS
- Equal-width KPI grids over stretch-to-fill cards
- Wrap text before truncating labels

---

## Colour palette

| Token | Role | Value |
|-------|------|-------|
| `--color-primary` | Brand / primary actions | `#5B54E8` |
| `--color-primary-hover` | Primary hover | `#4338CA` |
| `--color-secondary` | Secondary text / chrome | `#475569` |
| `--color-success` | Success / finished | `#16A34A` |
| `--color-warning` | Warning / rereading | `#D97706` |
| `--color-danger` | Danger / delete | `#DC2626` |
| `--color-text` | Body text | `#0F172A` |
| `--color-text-muted` | Secondary text | `#64748B` |
| `--color-text-subtle` | Captions / placeholders | `#94A3B8` |
| `--color-background` | Page background | `#F4F5F9` |
| `--color-surface` | Cards / panels | `#FFFFFF` |
| `--color-border` | Borders | `#E5E7EB` |
| `--color-hover` | Row / control hover | soft primary tint |

Legacy aliases (`--color-bg`, `--color-text-primary`, `--color-primary-dark`, …) remain for older rules in `style.css`. Prefer the canonical names above for new work.

### Theme system (v1.1)

Appearance modes: **Light**, **Dark**, **Follow System** (default).

| Layer | Responsibility |
|-------|----------------|
| `html[data-theme="light\|dark"]` | Active resolved theme |
| `html[data-theme-pref]` | Saved preference (`light` / `dark` / `system`) |
| `static/js/theme.js` | Theme Manager (persist, apply, system watch, charts) |
| `design-system.css` | Light + dark token sets |
| `localStorage` key `kwalitec-theme` | Client-only preference (no DB) |

Semantic aliases also available: `--bg`, `--surface`, `--surface-alt`, `--card`, `--primary`, `--text`, `--border`, `--input`, `--chart-grid`, `--chart-text`, etc.

Dark palette is intentional (charcoal surfaces, not inverted light). Book covers and uploaded images are never recolored.

Settings → Appearance controls preference; changes apply immediately with colour-only transitions.

---

## Spacing

| Token | Value |
|-------|-------|
| `--space-xs` | 4px |
| `--space-sm` | 8px |
| `--space-md` | 16px |
| `--space-lg` | 24px |
| `--space-xl` | 32px |
| `--space-2xl` | 48px |

Section gaps use `--space-lg`. Card padding uses `--space-md`.

---

## Radius

| Token | Value |
|-------|-------|
| `--radius-sm` | 8px (controls, buttons) |
| `--radius-md` | 12px (cards) |
| `--radius-lg` | 16px (large panels) |
| `--radius-full` | pills / badges |

---

## Typography

| Class | Use |
|-------|-----|
| `.type-page-title` | Page title |
| `.type-section-title` | Section eyebrow / uppercase label |
| `.type-card-title` | Card title |
| `.type-subtitle` | Supporting line under titles |
| `.type-body` | Body copy |
| `.type-caption` | Captions |
| `.type-meta` | Metadata / timestamps |

Font scale tokens: `--font-xs` → `--font-display`.

Family: Inter via `--font-family`.

Existing page classes (`.page-intro-title`, `.rs-section-title`, …) are mapped onto this scale in `design-system.css`.

---

## Layout / grid

| Class | Purpose |
|-------|---------|
| `.ds-container` | Max-width page shell |
| `.ds-content` | Narrow content column |
| `.ds-page` | Vertical page stack |
| `.ds-page-header` | Title + primary actions row |
| `.ds-kpi-grid` / `.ds-grid--kpi` | Equal KPI cards |
| `.ds-card-grid` | Book / card grids |
| `.ds-grid--analytics` | Chart panels |

KPI rows (`.rs-kpi-row`, `.hub-kpi-row`, `.authors-stats`) already use the shared equal-width grid behaviour.

**Page structure (recommended)**

1. Page title (+ optional subtitle)
2. Primary actions
3. Summary / KPIs
4. Main content
5. Secondary content

---

## Buttons

Base: `.btn` or `.ds-btn`

| Modifier | Use |
|----------|-----|
| `.btn--primary` | Main action |
| `.btn--secondary` | Alternative |
| `.btn--outline` | Quiet emphasis |
| `.btn--danger` | Destructive |
| `.btn--ghost` | Tertiary |
| `.btn--icon` | Icon-only |
| `.btn--sm` / `.btn--lg` | Sizes |

Existing CTAs (`.db-cta`, `.btn-primary`, `.home-continue-btn`, …) inherit the same height, radius, and hover behaviour.

Disabled: `:disabled` or `.is-disabled`.

---

## Forms

Use `.form-control` / `.ds-input` / `.ds-select` / `.ds-textarea`.

All text inputs, selects, and search fields share:

- height `--control-height` (40px)
- radius `--radius-sm`
- focus ring `--color-focus-ring`
- font `--font-md`

Labels: `.form-label` / `.ds-label`.

---

## Cards

Base: `.card` / `.ds-card`

Variants: `--surface`, `--analytics`, `--book`, `--goal`, `--admin`, `--compact`, `--static`.

Shared: radius, border, shadow, subtle hover lift.

Feature cards (`.lib-card`, `.rs-kpi-card`, `.hub-kpi-card`, …) map onto the same surface language.

---

## Badges

Base: `.badge` / `.ds-badge`

| Modifier | Meaning |
|----------|---------|
| `--finished` | Finished |
| `--reading` | Currently reading |
| `--want` | Want to read |
| `--dnf` | Did not finish |
| `--rereading` | Rereading |
| `--wild` | Wild |
| `--favourite` | Favourite quote |
| `--rating` | Rating chip |
| `--success` / `--warning` / `--danger` | System status |

Reading status chips use `status_chip.html` (`.badge` + `.status-chip--*`).

---

## Icons

| Class | Size |
|-------|------|
| `.icon--sm` / `.ds-icon--sm` | 14px |
| `.icon--md` / `.ds-icon--md` | 16px |
| `.icon--lg` / `.ds-icon--lg` | 20px |

Align icons with text using inline-flex wrappers.

---

## Tables

Use `.table` / `.ds-table` (or existing `.hub-data-table` / `.admin-table`).

Wrap with `.table-wrap` / `.ds-table-wrap`.

Includes: sticky headers, comfortable row padding, hover highlight.

Admin Library, Authors, Users, and User Detail should all use this table language.

---

## Empty states

Partial: `templates/components/empty_state.html`

```jinja
{% with title='Add your first book.',
        description='Ratings, quotes, and your reading year grow from here.',
        action_href=url_for('add'),
        action_label='Add Book',
        action_class='open-add-modal' %}
{% include 'components/empty_state.html' %}
{% endwith %}
```

Structure: icon → title → description → primary action → optional secondary action.

Visual classes: `.empty-state`, `.empty-state__icon`, `.empty-state__title`, `.empty-state__desc`, `.empty-state__actions`.

---

## Shadows & motion

| Token | Use |
|-------|-----|
| `--shadow-sm` | Default cards |
| `--shadow-md` | Hover / elevated |
| `--shadow-lg` | Modals / strong elevation |
| `--transition-fast` | Focus / border |
| `--transition-normal` | Hover / lift |

Respect `prefers-reduced-motion`.

---

## Responsiveness

Breakpoints used by the foundation:

- **≤1100px** — analytics charts stack
- **≤900px** — 3/4 grids → 2 columns
- **≤720px** — KPI grids → 2 columns; page header stacks
- **≤480px** — card grids → single column

Avoid horizontal scrolling, oversized whitespace, and truncated KPI labels.

---

## Rules for future pages

1. Import tokens from `design-system.css` — do not redefine colours.
2. Compose with `.btn`, `.ds-card`, `.badge`, `.ds-kpi-grid`, `.empty-state`.
3. Add page-specific CSS to `style.css` only when a primitive cannot express the need.
4. Never hard-code hex values for brand colours when a token exists.
5. Keep page order: title → actions → summary → main → secondary.
6. No schema, migration, or URL changes for UI-only work.

---

## Accessibility

- Visible `:focus-visible` rings on interactive controls
- Sticky table headers for long admin lists
- Empty states expose `role="status"` where appropriate
- Reduced motion respected globally
