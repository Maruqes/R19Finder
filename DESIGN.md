---
name: R19 Finder
description: Dark workspace for vehicle profiles and part research
colors:
  background: "#111212"
  surface: "#191a1a"
  sidebar: "#171918"
  foreground: "#efefec"
  secondary-text: "#a1a6a2"
  primary: "#ef965f"
  primary-text: "#221409"
  border: "#303331"
  input-border: "#3a3d39"
  success: "#a4c6a8"
  warning: "#dec17e"
  error: "#ed8e89"
typography:
  headline:
    fontFamily: Geist Variable, sans-serif
    fontSize: 30px
    fontWeight: 550
    lineHeight: 1.2
    letterSpacing: -0.035em
  body:
    fontFamily: Geist Variable, sans-serif
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.55
  section:
    fontFamily: Geist Variable, sans-serif
    fontSize: 17px
    fontWeight: 550
    letterSpacing: -0.015em
rounded:
  control: 8px
  surface: 12px
spacing:
  field-gap: 20px
  section-gap: 24px
  page-inset: 38px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-text}"
    rounded: "{rounded.control}"
    height: 40px
  form-surface:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.surface}"
    padding: 25px
---

## Overview

A dark workshop workspace built for reading part descriptions, comparing evidence and keeping track of ongoing research. The user’s dark-only direction applies across all screens. Operational clarity carries the visual identity: charcoal layers, small orange actions, precise typography, visible boundaries and full-frame reference photography.

## Colors

The normative runtime tokens live in frontend/src/styles.css. Orange identifies primary actions, links and current selections. Success, queue and failure colors supplement written state labels. Most content uses the neutral foreground and secondary-text tokens.

## Typography

Geist Variable is bundled and served locally. Page headings are 30px on larger screens and 27px at narrower breakpoints; section headings are 17px. Form controls increase to 16px on mobile. Dates and counts use tabular numerals. Descriptions and reports have a maximum reading width of 75ch.

## Layout

A 240px navigation rail frames the desktop workspace, reducing to 210px below 1250px. Below 760px it becomes a shadcn Sheet. Dashboard requests occupy the main column, with a narrower vehicle gallery column; those sections stack below 1000px. Forms use a primary editing column and a contextual side column. Mobile form groups collapse structurally, not by shrinking controls.

## Elevation & Depth

Resting surfaces use borders and tonal differences. Popovers and dialogs use a soft 0 16px 50px shadow. No page-load choreography or decorative glow.

## Shapes

Containers use 12px corners. Controls use the shared shadcn radius, approximately 8px. Small status badges carry a dot and an explicit label. Photo frames use object-fit contain and preserve the complete source image.

## Components

shadcn supplies buttons, inputs, textareas, labels, checkboxes, selects, tabs, sheets, dialogs, badges and skeletons. Selects and modal styles use per-response CSP nonces. Every form control has a label, and primary mobile controls are at least 44px tall.

Motion is reserved for gallery image changes and selection feedback. Reduced-motion users start with paused galleries and instantaneous photo transitions. Gallery rotation also pauses on hover, focus and hidden documents.

Part facts distinguish user-supplied, AI-suggested and user-confirmed information. Accepting an AI suggestion does not label it verified. Listing cards preserve availability and fitment uncertainty.

## Do's and Don'ts

- Do keep every surface dark, including menus and browser form affordances.
- Do use the same button, field and status vocabulary on every route.
- Do provide actionable empty states and errors with recovery guidance.
- Do retain real content, full photo proportions and server validation.
- Don't use gradients, decorative charts, fabricated results or large promotional heroes.
- Don't auto-apply conflicting AI suggestions or imply unverified listings are confirmed matches.
