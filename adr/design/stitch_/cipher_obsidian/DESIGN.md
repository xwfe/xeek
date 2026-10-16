---
name: Cipher Obsidian
colors:
  surface: '#0f131c'
  surface-dim: '#0f131c'
  surface-bright: '#353943'
  surface-container-lowest: '#0a0e17'
  surface-container-low: '#181b25'
  surface-container: '#1c1f29'
  surface-container-high: '#262a34'
  surface-container-highest: '#31353f'
  on-surface: '#dfe2ef'
  on-surface-variant: '#bbcabf'
  inverse-surface: '#dfe2ef'
  inverse-on-surface: '#2c303a'
  outline: '#86948a'
  outline-variant: '#3c4a42'
  surface-tint: '#4edea3'
  primary: '#4edea3'
  on-primary: '#003824'
  primary-container: '#10b981'
  on-primary-container: '#00422b'
  inverse-primary: '#006c49'
  secondary: '#4cd7f6'
  on-secondary: '#003640'
  secondary-container: '#03b5d3'
  on-secondary-container: '#00424e'
  tertiary: '#c0c1ff'
  on-tertiary: '#1000a9'
  tertiary-container: '#9699ff'
  on-tertiary-container: '#1d17b2'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#6ffbbe'
  primary-fixed-dim: '#4edea3'
  on-primary-fixed: '#002113'
  on-primary-fixed-variant: '#005236'
  secondary-fixed: '#acedff'
  secondary-fixed-dim: '#4cd7f6'
  on-secondary-fixed: '#001f26'
  on-secondary-fixed-variant: '#004e5c'
  tertiary-fixed: '#e1e0ff'
  tertiary-fixed-dim: '#c0c1ff'
  on-tertiary-fixed: '#07006c'
  on-tertiary-fixed-variant: '#2f2ebe'
  background: '#0f131c'
  on-background: '#dfe2ef'
  surface-variant: '#31353f'
  surface-base: '#090D16'
  surface-raised: '#0F172A'
  surface-card: '#131C2E'
  surface-overlay: '#1E293B'
  status-danger: '#EF4444'
  status-warning: '#F59E0B'
  status-info: '#06B6D4'
  status-otp: '#8B5CF6'
  text-primary: '#F8FAFC'
  text-muted: '#94A3B8'
  border-subtle: rgba(148, 163, 184, 0.12)
  border-highlight: rgba(16, 185, 129, 0.35)
typography:
  headline-xl:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Geist
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Geist
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  code-otp:
    fontFamily: JetBrains Mono
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 36px
    letterSpacing: 0.15em
  code-secret:
    fontFamily: JetBrains Mono
    fontSize: 15px
    fontWeight: '500'
    lineHeight: 22px
    letterSpacing: 0.04em
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.06em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.08em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-mobile: 0.75rem
  margin: 1rem
  margin-tablet: 1.5rem
  space-2xs: 0.25rem
  space-xs: 0.5rem
  space-sm: 0.75rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
  space-2xl: 3rem
---

## Brand & Style

This design system defines an ultra-secure, privacy-centric mobile self-hosted password management experience. Built for technologists, security analysts, and sovereignty-oriented users, the aesthetic unites dark-mode cyber minimalism with tactile security reinforcement. 

The aesthetic philosophy balances precision engineering with reassuring cryptographic solidity. Instead of flat, utilitarian starkness, it employs subtle obsidian glass layers, micro-machined border highlights, and focused chromatic glows. The emotional intent is absolute certainty, impenetrable defense, and frictionless velocity. Every interaction delivers immediate visual and tactical feedback—reinforcing zero-knowledge architecture through clean geometry, tactical badges, and unambiguous typographic hierarchy.

## Colors

The system uses a calibrated dark spectrum optimized for high-contrast legible security telemetry and low visual fatigue during high-focus tasks.

- **Primary (`#10B981`)**: Electric Emerald serves as the primary affirmation color, indicating encrypted status, master unlocks, robust password health, and verified vault syncs.
- **Secondary (`#06B6D4`)**: Cyber Cyan provides secondary emphasis, highlighting interactive telemetry, passkey triggers, and active biometric scan zones.
- **Tertiary (`#6366F1`) & 2FA Accent (`#8B5CF6`)**: Electric Indigo and Violet isolate dynamic temporal secrets such as time-based one-time passwords (TOTP), hardware keys, and token lifecycles from static data.
- **Status Accents**: Pure Crimson (`#EF4444`) commands attention for exposed breaches and weak hashes; Amber (`#F59E0B`) flags pending audits and expiring tokens.
- **Neutral & Obsidian Base**: `#090D16` serves as canvas depth, layered with `#0F172A` and `#1E293B` to build crisp surface elevation without gray washout.

## Typography

Typographic scale prioritizes instant clarity and zero ambiguity between visually similar characters (such as `0` vs `O`, `1` vs `l`).

- **Interface Text**: Handled by **Geist**, providing low geometric distortion, neutral forms, and tight spacing suited for high-density mobile lists.
- **Monospace & Secret Handling**: **JetBrains Mono** is mandatory for all sensitive payload structures—passwords, hex keys, recovery seeds, passkey certificates, and TOTP tickers.
- **Numbers & Counters**: Always use tabular numbers (`tnum`) across both typefaces to eliminate layout jitter when OTP counters decrement or vault sizes calculate.
- **Casing & Hierarchy**: Micro-labels, credential types, and cipher statuses use uppercase JetBrains Mono with generous tracking (`0.06em` to `0.08em`) to anchor contextual authority.

## Layout & Spacing

Layout geometry follows an 8-point base module with a supplementary 4-point micro-scale for compact security tags and indicator badges.

- **Mobile First Canvas**: The primary interface conforms to single-column, thumb-driven zones. The bottom 45% of the mobile viewport is preserved for high-frequency interactions (quick copy, reveal secret, auto-fill triggering).
- **Vault Grouping**: Content stacks in distinct functional cards with strict vertical separation (`space-sm` between items in a collection, `space-lg` between audit categories).
- **Adaptive Breakpoints**:
  - `Mobile (< 640px)`: Full-width cards with `1rem` outer margins. Bottom sheet modals for authentication confirmations.
  - `Tablet / Foldable (≥ 640px)`: Master-detail split-view; left sidebar (320px) hosts categories and health scores, right pane surfaces credential inspection with `1.5rem` canvas gutters.

## Elevation & Depth

Depth is established through dark-field luminescence and tonal layering rather than high-contrast drop shadows.

- **Level 0 (Canvas Base)**: Deep obsidian `#090D16`. Zero elevation.
- **Level 1 (Card/Container)**: Background `#0F172A` with a micro-stroke `1px solid rgba(148, 163, 184, 0.08)`. Receives subtle top-down directional lighting via an inner gradient: `linear-gradient(180deg, rgba(255, 255, 255, 0.03) 0%, rgba(255, 255, 255, 0) 100%)`.
- **Level 2 (Active Item / Expanded Record)**: Background `#131C2E`, border `1px solid rgba(16, 185, 129, 0.25)`, accompanied by a concentrated emerald glow: `box-shadow: 0 4px 20px -2px rgba(16, 185, 129, 0.12)`.
- **Level 3 (Modal / Biometric Gate)**: Floating sheet `#1E293B` over a 60% darkened, blurred backdrop (`backdrop-filter: blur(16px)`). Bound by `1px solid rgba(255, 255, 255, 0.12)` with ambient shadow `0 20px 40px -8px rgba(0, 0, 0, 0.7)`.

## Shapes

The geometric signature uses precision-rounded radii (`0.5rem` standard / `8px`, scaling to `1rem` / `16px` on parent card groupings).

- **Standard Containers**: Use `rounded-lg` (`1rem`) to present a robust, shielded enclosure.
- **Interactive Inputs & Secret Fields**: Use base `rounded` (`0.5rem`) to feel technical and machined.
- **Security Badges & TOTP Tills**: Use pill geometry (`9999px`) exclusively for ephemeral, status-bound microchips (such as security strength indicators or cryptographic tags).
- **Shield Badges & Crests**: Feature chamfered or rounded shield geometries to anchor security trust markers at top-level navigation headers.

## Components

### Buttons & Interactive Triggers
- **Primary Action (Unlock, Authenticate, Save)**: Solid `#10B981` background with rich dark `#090D16` text in medium weight. Active states trigger an inner highlight and an emerald edge glow (`0 0 12px rgba(16, 185, 129, 0.4)`).
- **Secondary Action (Generate, Filter)**: Translucent tint `rgba(30, 41, 59, 0.8)` with a crisp `1px solid rgba(148, 163, 184, 0.2)` border, text in `#F8FAFC`.
- **Destructive Action (Revoke, Delete Vault)**: Dark crimson tint with `#EF4444` border and text. Never filled unless placed in a confirmation dialog.

### Secret & Password Display Field
- Monospaced JetBrains Mono typography with alternate character styling.
- Obfuscated bullets (`••••••••`) render with identical monospaced spacing as revealed text to eliminate card height reflow when toggling visibility.
- Include one-tap contextual quick-copy with a temporary checkmark indicator and haptic trigger pulse.

### 2FA / TOTP Cards
- Prominent `code-otp` centered typography in `#8B5CF6`.
- Integrated SVG circular countdown timer running along the edge or side, shifting from Emerald to Amber under 5 seconds remaining.

### Input Fields & Search
- Recessed slate background (`#0B1120`), inset border `1px solid rgba(148, 163, 184, 0.15)`.
- Focus state activates a 1px border highlight in `#06B6D4` paired with an ultra-soft cyan blur glow.

### Password Strength Meter
- Multi-segment segmented bar with 4 discrete blocks rather than a continuous bar, preventing vague estimations.
- Colors transition strictly: Danger (`#EF4444`), Warning (`#F59E0B`), Good (`#06B6D4`), Robust (`#10B981`).