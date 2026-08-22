---
name: Hublet
description: A restrained dark quick-glance dashboard for five personal-memory plugins.
colors:
  ground: "#0b0d10"
  surface: "#14181d"
  surface-raised: "#1a1f25"
  line: "#2c333b"
  line-strong: "#414b56"
  text: "#f2f5f7"
  muted: "#a9b2bc"
  focus: "#8ac7ff"
  goals: "#9bd47b"
  food: "#efb56a"
  recipes: "#ec8d82"
  coffee: "#79bce8"
  health: "#b6a2f2"
  field: "#101318"
  inset: "#0f1216"
  error-ground: "#321713"
  error-text: "#ffd5d0"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.125
    letterSpacing: "normal"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 700
    lineHeight: 1.2
  reading:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, system-ui, sans-serif"
    fontSize: "clamp(1.15rem, 3vw, 1.8rem)"
    fontWeight: 750
    lineHeight: 1.2
  reading-compact:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 750
    lineHeight: 1.2
  login-display:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, system-ui, sans-serif"
    fontSize: "clamp(2rem, 8vw, 3rem)"
    fontWeight: 700
    lineHeight: 1.125
  launcher:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, system-ui, sans-serif"
    fontSize: "clamp(1.05rem, 3.2vw, 2.15rem)"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "normal"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, Segoe UI, system-ui, sans-serif"
    fontSize: "0.82rem"
    fontWeight: 650
    lineHeight: 1.45
rounded:
  control: "12px"
  panel: "14px"
spacing:
  tight: "0.5rem"
  compact: "0.65rem"
  base: "1rem"
  panel-edge: "clamp(1rem, 3vw, 1.75rem)"
  section: "clamp(3rem, 8vw, 6rem)"
components:
  button-primary:
    backgroundColor: "{colors.text}"
    textColor: "{colors.ground}"
    rounded: "{rounded.control}"
    padding: "0.65rem 0.75rem"
    height: "44px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    rounded: "{rounded.control}"
    padding: "0.45rem 0.7rem"
    height: "40px"
  field:
    backgroundColor: "{colors.field}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "0.65rem 0.75rem"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.panel}"
    padding: "{spacing.panel-edge}"
  launcher-tile:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.panel}"
    padding: "clamp(0.7rem, 2.5vw, 1.35rem)"
  navigation-primary:
    backgroundColor: "{colors.ground}"
    textColor: "{colors.text}"
    height: "64px"
---

# Design System: Hublet

## Overview

**Creative North Star: "Night Instruments"**

Hublet is a compact bank of instruments used to check personal facts in seconds. Matte near-black infrastructure, ruled charcoal surfaces, pale readings, and one quiet signal color per plugin make the interface feel precise and calm without borrowing the spectacle of an analytics suite.

The system is native, factual, and dense enough for an iPhone. Status and charts occupy the first useful viewport; read-only history waits below. There are no ornamental layers, slogans, web fonts, or decorative motion. Lucide-derived line icons and tabular numerals carry most of the visual character.

**Key Characteristics:**

- Matte dark ground with bordered charcoal instrument surfaces.
- Modern system sans throughout, with tight headings and tabular readings.
- Restrained Goals, Food, Recipes, Coffee, and Health signal colors.
- A compact two-column launcher built for up to eight plugins.
- Inline charts and current status before history or definitions.

## Colors

The palette is almost monochrome infrastructure with five semantic plugin signals. Accent color identifies a domain and highlights its live readings; it does not fill large surfaces.

### Primary

- **Night Ground:** The continuous page canvas, header, and inverse text color for filled actions.
- **Instrument White:** Primary text, shared filled actions, and the highest-contrast reading color.
- **Focus Blue:** The global visible keyboard outline on links and controls.

### Secondary

- **Goal Signal:** Goal progress values, chart traces, completed states, and Goals actions.
- **Food Signal:** Nutrition readings, weekly bars, the monthly line, and Food identity. Food is read-only in the dashboard, so this color does not imply an editing action.
- **Recipe Signal:** Recipe readings, rating traces, and Recipes actions.
- **Coffee Signal:** Coffee readings, extraction traces, and Coffee actions.
- **Health Signal:** HealthKit measurements, freshness, and Health identity.

### Tertiary

- **Error Ground / Error Text:** A warm, dark alert pair used for server-returned form errors.

### Neutral

- **Instrument Surface:** Default launcher tiles, panels, and management surfaces.
- **Raised Surface:** Hover feedback for launcher tiles and quiet buttons.
- **Rule / Strong Rule:** Dividers, panel edges, chart baselines, and form control boundaries.
- **Muted Reading:** Labels, metadata, timestamps, captions, navigation links, and empty states.
- **Field / Inset:** Dark recessed fills for inputs, code, and chart tracks.

### Named Rules

**The Signal, Not Surface Rule.** Plugin colors belong on icons, live values, chart marks, and contextual actions; large panels stay neutral.

**The Food Means Read Rule.** Food may use its amber signal for nutrition status, but the web dashboard exposes no Food mutation controls.

## Typography

**Display Font:** Native system sans, led by San Francisco on Apple platforms

**Body Font:** The same native system sans stack

**Character:** One modern system face keeps the interface immediate and dependency-free. Hierarchy comes from size, weight, tight tracking, color, and tabular numerals rather than a decorative display family.

### Hierarchy

- **Display:** Tight, responsive page titles for plugin identity and authentication states.
- **Launcher:** Large, compact destination names that remain legible inside short tiles.
- **Title:** One-rem panel headings and semibold record identities; keep headings terse.
- **Body:** Root-size operational copy, filters and records with a compact 1.45 line height.
- **Label:** Small, muted, semibold field labels, chart captions, metadata, and navigation.
- **Readings:** Bold responsive values in tabular numerals; color them with the current plugin signal.

### Named Rules

**The One Native Voice Rule.** Do not introduce web fonts or a separate display face; the system sans is part of Hublet's speed and restraint.

**The Numbers Hold Still Rule.** Measurements, counts, dates, chart endpoints, and status numerals use tabular figures wherever alignment changes over time.

## Layout

The shared shell is centered at a maximum width of 1120px. It uses 1rem side gutters on wider screens and 0.5rem gutters at 760px and below. The header is a fixed-height 64px rail, while page content remains in normal document flow.

The launcher fills the remaining small viewport height and always uses two equal columns. With one to eight plugins, rows flex to fit and overflow is suppressed; this keeps the approved Goals, Food, Recipes, Coffee, Health order visible without scrolling on an iPhone 17 and preserves room for three more destinations. Beyond eight, rows receive a 112px minimum and the launcher may scroll.

Plugin pages place a compact title and Week/Month segmented control above an instrument panel. The Hublet wordmark is larger than plugin titles and provides the only Home affordance. Most instrument panels fill the first useful viewport; Goals stays content-sized so inactive data does not create empty space. Current readings, progress and inline charts come first; a deliberate gap separates them from read-only history and Food catalogue filters.

In-page cues use native smooth scrolling. The reduced-motion preference restores immediate scrolling.

**The Read, Then Inspect Rule.** Every plugin opens on current status; optional histories begin below the first instrument panel only where they remain useful.

**The Eight-Fit Rule.** Preserve the launcher's two-column, viewport-fitted behavior for up to eight destinations; do not turn it into a scrolling card feed at the supported limit.

## Elevation & Depth

Hublet uses no box shadows. Tonal layering and one-pixel rules create all depth: Night Ground supports Instrument Surface, recessed fields use Field or Inset, and hover moves one tonal step to Raised Surface. Charts remain drawn directly into the panel rather than floating in nested cards.

### Named Rules

**The Ruled, Not Raised Rule.** Boundaries come from color and lines; never add shadows to panels, tiles, navigation, or controls.

## Shapes

The control language is restrained and slightly softened. Main panels and launcher tiles use broad 14px corners; filters and error messages use 12px corners. Records, histories, reading groups, and chart tracks rely on straight one-pixel dividers inside those outer shapes rather than nesting rounded cards.

Icons are Lucide-derived, unfilled, round-capped line drawings with a 24px view box and a 2px stroke. Their geometry stays recognizable and functional; plugin signal color supplies identity.

**The Outer Radius Rule.** Round the containing instrument, not every row inside it.

## Components

### Buttons

- **Primary:** At least 44px tall, bold, and inverted; shared actions use Instrument White, while plugin actions use the current signal color.
- **Quiet:** A compact 40px secondary control with muted text, a strong rule, and no fill until hover.
- **Hover / Focus:** Hover changes tone without movement. Keyboard focus always uses the 3px Focus Blue outline with a 3px offset.

### Launcher Tiles

- **Structure:** A two-column internal grid pairs a responsive line icon with a clipped name-and-summary block.
- **State:** Neutral Instrument Surface at rest; Raised Surface and a stronger border on hover. Tiles never lift, scale, or acquire shadows.
- **Order:** Goals, Food, Recipes, Coffee, Health is the shipped primary sequence. Future plugins append without disturbing that order unless product priority changes.

### Instrument Panels and Charts

- **Panel:** One bordered neutral surface owns the first useful viewport.
- **Readings:** Four values appear in a ruled grid; on compact screens it becomes a two-by-two matrix.
- **Charts:** Inline SVG line charts and CSS bar charts use strong-rule baselines, muted target lines, and the current plugin signal for data. Empty states remain centered and quiet.

### Filters / Fields

- **Style:** Recessed Field fill, Strong Rule border, 12px corners, visible sentence-case labels, and native controls.
- **Focus:** The same global Focus Blue outline used across the application.
- **Use:** Fields are limited to authentication and read-only Food catalogue filtering.

### Records

- **Style:** Native disclosure rows inside one bordered records panel, with internal rules and at least 68px summary height.
- **Body:** Observations, cook logs, evidence, and histories open in place. Measurements align opposite identity on wide screens and stack left on compact screens.

### Navigation

- **Desktop:** A 64px Night Ground rail with the Hublet wordmark, plugin links in shipped order, and an icon-only sign-out action.
- **Mobile:** Plugin links hide; the wordmark remains a Home affordance and sign-out retains a 44px target.

### Food Status

- **Read-only:** Food shows seven daily bars or a same-height thirty-day line, a native meal disclosure, four readings underneath, and a ten-result nutrition catalogue. Month uses five date anchors and one latest-value callout. The catalogue defaults to Grain facts; estimates are explicitly included with one checkbox.

### Goals Status

- **Read-only:** Goals separates active Health, Career and Social goals into content-sized category panels. Current values stay beside titles; target values label their dashed chart line. Numeric supporting evidence expands beneath its primary chart, while definitions, statuses, sources, prose, and inactive goals stay out of the dashboard.

### Health Status

- **Read-only:** Health shows global freshness, four mapped measurements and compact inline trends. Raw records and synchronization stay in MCP rather than the dashboard.

## Do's and Don'ts

### Do:

- **Do** keep the first useful viewport devoted to current status, progress, and charts.
- **Do** preserve the compact two-column launcher and the Goals, Food, Recipes, Coffee, Health order.
- **Do** use semantic server-rendered HTML, native disclosures, visible labels, and accessible SVG titles.
- **Do** keep all essential interaction targets at least 44px tall, except the intentionally compact 40px quiet button.
- **Do** use internal rules to organize dense records and histories inside one outer panel.

### Don't:

- **Don't** add shadows, gradients, glass effects, decorative animation, or ornamental card stacks.
- **Don't** introduce web fonts, icon fonts, external assets, JavaScript charts, or frontend-framework assumptions.
- **Don't** fill large surfaces with plugin colors or use those signals as decoration.
- **Don't** add plugin mutation controls to the web dashboard.
