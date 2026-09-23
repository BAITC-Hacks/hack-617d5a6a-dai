---
name: tailwind-v4
description: Tailwind CSS v4.3 rules for this project (CSS-first config in src/index.css, shadcn theme tokens, v3→v4 class renames, dark mode). Use this skill whenever writing or changing classNames, styling, colors, spacing, theme, dark mode, custom colors/fonts, or anything visual (стили, цвета, тема, верстка, dark mode, классы) — agents often write Tailwind v3 syntax that silently breaks in v4.
---

# Tailwind CSS v4.3 in this project

Most model training data is Tailwind v3. v4 changed configuration and renamed several utilities; some v3 syntax still compiles but produces broken or different CSS, so it fails silently.

## Configuration lives in CSS

- There is **no** `tailwind.config.js` / `postcss.config.js`. Never create them.
- Tailwind runs through `@tailwindcss/vite` (vite.config.ts). Content is detected automatically.
- The theme is in `src/index.css`: `:root` / `.dark` hold CSS variables (OKLCH colors from shadcn), `@theme inline { ... }` maps them to utilities.

Add a custom color:

```css
:root { --brand: oklch(0.65 0.2 145); }
.dark { --brand: oklch(0.75 0.18 145); }
@theme inline { --color-brand: var(--brand); }
```

Now `bg-brand`, `text-brand`, `border-brand/50` work. Custom utilities use `@utility name { ... }`, not `@layer components`.

## Use theme tokens, not raw colors

The UI is shadcn/ui (see the official `shadcn` skill). Use semantic tokens so light/dark and the chosen preset keep working:

| Purpose | Classes |
|---|---|
| page | `bg-background text-foreground` |
| surfaces | `bg-card text-card-foreground`, `bg-popover`, `bg-muted` |
| secondary text | `text-muted-foreground` |
| brand/action | `bg-primary text-primary-foreground` |
| danger | `text-destructive`, `bg-destructive` |
| borders/inputs | `border` (color comes from base layer), `border-input`, `ring-ring` |

Avoid `bg-white`, `text-gray-500`, `bg-blue-600` for anything that should follow the theme. Radius classes (`rounded-md`, `rounded-lg`, ...) are driven by the shadcn `--radius` variable in this project.

## v3 → v4 differences (verified on 4.3.3)

| v3 habit | v4 in this project | Why |
|---|---|---|
| `bg-[--brand]` | `bg-(--brand)` | v3 form now outputs invalid CSS (`background-color: --brand`) |
| `bg-opacity-50`, `text-opacity-*` | `bg-black/50`, `text-foreground/70` | opacity utilities removed |
| `shadow-sm` (small) | `shadow-xs` | scale shifted: v4 `shadow-sm` = old `shadow` |
| `blur-sm` (small) | `blur-xs` | same shift |
| `outline-none` to hide focus outline | `outline-hidden`, or keep `outline-none` only together with a visible `focus-visible:ring-*` (as shadcn components do) | v4 `outline-none` really removes the outline, including in forced-colors mode |
| `ring` (3px) | `ring-3` | v4 `ring` is 1px |
| `!flex` | `flex!` | important modifier goes at the end |
| `flex-shrink-0`, `flex-grow` | `shrink-0`, `grow` | old names deprecated |
| `overflow-ellipsis` | `text-ellipsis` | old name deprecated |
| `w-4 h-4` | `size-4` | shorter |

Also: variants stack left-to-right (`*:first:pt-0`); prefer `gap-*` over `space-y-*` in flex/grid layouts.

## Dark mode

`next-themes` toggles the `.dark` class on `<html>` (`ThemeProvider` in `src/main.tsx`). `dark:` works through `@custom-variant dark (&:is(.dark *));` in `src/index.css`. With tokens you rarely need `dark:` at all.

```tsx
import { useTheme } from 'next-themes'
const { resolvedTheme, setTheme } = useTheme()
setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')
```

## Conditional classes

Use `cn()` from `@/lib/utils` (merges and dedupes Tailwind classes):

```tsx
<div className={cn('rounded-lg border p-4', active && 'border-primary bg-primary/5', className)} />
```
