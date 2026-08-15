---
name: Hublet
description: A modular home wall organizer for three small personal-memory tools.
colors:
  ink: "#152431"
  muted-ink: "#526474"
  utility-ground: "#e9eef2"
  surface: "#ffffff"
  divider: "#cbd5dc"
  coffee: "#236bc5"
  coffee-bay: "#9bc5ff"
  goals: "#4d6f00"
  goals-bay: "#c9e96b"
  recipes: "#a33c27"
  recipes-bay: "#ff9f87"
  focus: "#0a72dc"
typography:
  display:
    fontFamily: "ui-rounded, SF Pro Rounded, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "clamp(3rem, 9vw, 5.5rem)"
    lineHeight: 0.94
    letterSpacing: "-0.04em"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "1.1rem"
    fontWeight: 800
    lineHeight: 1.5
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "0.86rem"
    fontWeight: 700
    lineHeight: 1.5
rounded:
  mark: "8px 8px 8px 2px"
  control: "10px"
  panel: "14px"
spacing:
  compact: "0.65rem"
  control-x: "0.8rem"
  base: "1rem"
  panel-edge: "1.1rem"
  section: "2rem"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "0.7rem 0.8rem"
    height: "44px"
  button-quiet:
    backgroundColor: "transparent"
    textColor: "{colors.muted-ink}"
    rounded: "{rounded.control}"
    padding: "0.45rem 0.7rem"
    height: "40px"
  field:
    backgroundColor: "#fbfcfd"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0.7rem 0.8rem"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "clamp(1.1rem, 3vw, 2rem)"
  launcher-coffee:
    backgroundColor: "{colors.coffee-bay}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "clamp(1.25rem, 3vw, 2rem)"
  launcher-goals:
    backgroundColor: "{colors.goals-bay}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "clamp(1.25rem, 3vw, 2rem)"
  launcher-recipes:
    backgroundColor: "{colors.recipes-bay}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "clamp(1.25rem, 3vw, 2rem)"
  navigation-primary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    height: "68px"
---

# Design System: Hublet

## Overview

**Creative North Star: "The Modular Home Wall Organizer"**

Hublet feels like a compact household fixture: three purpose-built bays mounted on cool utility gray, with ink-blue structure, precise labels, and soft molded depth. It is friendly and tactile without becoming decorative, gamified, or dashboard-like.

The interface is an operating surface for short, trusted-device sessions. Records stay visually primary, forms remain native and direct, and each plugin owns one saturated color family so the user always knows which bay they are working in.

**Key Characteristics:**

- Cool utility-gray ground with white working surfaces.
- Ink structure and a distinct saturated family for each plugin.
- Rounded display voice paired with restrained system UI text.
- Molded panels, fine dividers, and soft offset depth.
- Mobile-first task order with one reduced-motion-safe settle.

## Colors

The palette keeps shared infrastructure cool and quiet while Coffee, Goals, and Recipes each receive a recognizable accent and a lighter launcher bay.

### Primary

- **Organizer Ink:** Shared text, navigation, brand mark, and default action color.
- **Focus Blue:** A consistent, high-contrast keyboard focus outline across all controls.

### Secondary

- **Coffee Blue:** Coffee actions and contextual emphasis.
- **Goal Green:** Goal actions and contextual emphasis.
- **Recipe Terracotta:** Recipe actions and contextual emphasis.

### Tertiary

- **Coffee Bay Blue:** The Coffee launcher panel and brand-mark layer.
- **Goal Bay Lime:** The Goals launcher panel and brand-mark layer.
- **Recipe Bay Coral:** The Recipes launcher panel.

### Neutral

- **Utility Ground:** The cool page canvas surrounding the organizer surfaces.
- **Work Surface:** Cards, rails, login, and error containers.
- **Muted Ink:** Supporting copy, labels, metadata, measurements, and quiet actions.
- **Divider Gray:** Structural borders, record separators, and helper-note outlines.

### Named Rules

**The One Bay, One Family Rule.** A plugin uses only its assigned dark accent for actions and its matching light bay on the launcher.

**The Cool Infrastructure Rule.** Shared chrome stays ink, white, or utility gray; plugin color communicates place, not decoration.

## Typography

**Display Font:** UI Rounded, with SF Pro Rounded and the system sans stack as fallbacks  
**Body Font:** System UI, with Segoe UI and sans-serif fallbacks

**Character:** Large, close-set rounded headings make a small utility feel domestic and approachable. System UI handles every working label, field, record, and measurement for speed and native familiarity.

### Hierarchy

- **Display:** Tight line height and negative tracking for page and error headings; keep primary headings near a compact twelve-character measure.
- **Launcher Title:** Rounded, bold, close-set type sized responsively between compact and wide layouts.
- **Title:** Heavy system text for action-panel summaries, navigation landmarks, counts, and strong actions.
- **Body:** Native system text at the browser root size for records, instructions, and form content; explanatory page copy is capped at 62 characters.
- **Label:** Compact, bold system text in muted ink; labels remain sentence case.

### Named Rules

**The Rounded Voice Rule.** Rounded type speaks only for identity and major destinations; operational copy always returns to the system sans.

## Layout

The shared shell is centered at a maximum width of 1120px with responsive side gutters. Desktop plugin pages use a fluid records column beside a 290–360px action rail; the launcher uses one slightly larger first bay followed by two equal bays.

At 760px and below, every grid becomes a single column. The action rail moves before records so the common manual action arrives first on a phone, two-column forms collapse, history rows stack, and destination links hide while the brand and sign-out control remain. Touch actions maintain at least 44px height, except the intentionally compact 40px quiet action.

Spacing uses a compact working rhythm around controls and records, then larger responsive gaps between page-level regions. Panels use fluid edge padding; headings receive substantially more separation than fields or list rows.

**The Task-First Mobile Rule.** Responsive reordering follows what the owner came to do, not desktop source order.

## Elevation & Depth

Hublet uses a hybrid of tonal layering and soft offset shadows. White working surfaces and saturated launcher bays lift from the utility ground with a diffuse low shadow; bordered action panels and helper notes remain attached to the wall. Hover deepens a launcher bay's shadow without moving it.

### Shadow Vocabulary

- **Panel Depth:** `0 10px 24px rgb(21 36 49 / 12%)` for launcher bays, record panels, login, and error surfaces.
- **Bay Hover:** `0 14px 30px rgb(21 36 49 / 18%)` for launcher-card hover only.
- **Mark Depth:** `0 7px 16px rgb(21 36 49 / 16%)` for the layered Hublet mark.

### Named Rules

**The Attached Rail Rule.** Secondary action and helper panels use borders, not shadows; depth is reserved for primary surfaces and destinations.

## Shapes

The form language is softly molded: working panels and launcher bays use broad 14px corners, controls and messages use 10px corners, and the 28px brand tile uses an asymmetric 8px corner set with a tighter lower-left corner. Thin dividers organize record density without nesting extra cards.

**The Panel, Not Card Stack Rule.** Use one molded container with internal dividers for a record collection; do not wrap every row in its own floating card.

## Components

### Buttons

- **Shape:** Gently rounded controls with a minimum 44px touch height and heavy labels.
- **Primary:** Ink in shared contexts; Coffee Blue, Goal Green, or Recipe Terracotta inside the matching plugin page.
- **Hover / Focus:** Preserve the contextual fill and use the global 3px Focus Blue outline with a 3px offset for keyboard focus.
- **Quiet:** Transparent with muted text and a Divider Gray stroke; hover shifts to a faint cool surface and darker border.

### Launcher Bays

- **Shape:** Large molded destinations with broad corners and generous fluid padding.
- **Color:** One light plugin color per bay, always with Organizer Ink content.
- **Content:** A 64px line icon, rounded destination title, short factual summary, and explicit Open action.
- **State:** Hover deepens only the ambient shadow; layout and color remain stable.

### Cards / Containers

- **Working Panel:** White surface, broad corners, responsive internal padding, and Panel Depth.
- **Action Panel:** White surface, broad corners, Divider Gray border, and no shadow.
- **Helper Note:** White bordered panel with compact padding and muted supporting text.

### Inputs / Fields

- **Style:** Near-white fill, cool gray stroke, 10px corners, compact internal padding, and ink text.
- **Focus:** The same visible Focus Blue outline used throughout the application.
- **Error:** A warm pale message surface with dark terracotta text; errors use `role="alert"` and sit beside the affected form.

### Records

- **Style:** Native disclosure rows separated by thin dividers inside one records panel.
- **Summary:** At least 76px tall, with primary identity on the left and action or measurement on the right.
- **Body:** Editing, progress, or history content opens in place; measurements use tabular numerals.

### Navigation

- **Desktop:** A 68px white rail with the layered Hublet mark, direct plugin links, and a quiet sign-out control.
- **Mobile:** Hide plugin links and retain the home mark plus a compact full-width sign-out control in the trailing slot.

### Motion

The page settles once on entry over 360ms using a fast-out easing curve, fading from 0.88 opacity while moving upward by 6px. Disable the motion entirely when reduced motion is requested; no other component animation is part of the system.

## Do's and Don'ts

### Do:

- **Do** keep records and the current plugin's primary action in the first useful viewport.
- **Do** use semantic server-rendered controls, native disclosures, and visible labels.
- **Do** use internal dividers to organize dense history inside one molded working panel.
- **Do** preserve the single settle motion and its reduced-motion override.

### Don't:

- **Don't** turn Hublet into an analytics dashboard, plugin marketplace, or generic productivity shell.
- **Don't** mix plugin color families or spread saturated color into shared navigation and infrastructure.
- **Don't** create a floating card for every row or add ornamental depth to secondary rails.
- **Don't** replace the system UI body voice with a decorative typeface.
