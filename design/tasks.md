## Project Brief

- Date: 2026-05-03
- Project type: Existing web dashboard for OpsBob incident response.
- Platform: Web, desktop-first operational console.
- Visual system: Carbon g100 theme with existing OpsBob dark tokens and IBM Plex Mono.
- Current layout: Three-panel dashboard with incident feed on the left, Bob analysis in the center, and command/control widgets on the right.
- User goal: Add a live agent orchestration view for brainstorm -> plan -> execute with live outputs.
- Constraint: Prefer conservative refinements, reuse existing design system/colors, avoid new visual concepts.

## Research Findings

- Carbon disclosure guidance: use disclosures only for secondary, user-initiated content; do not hide critical workflow information inside a disclosure/popover.
- Carbon disclosure guidance: keep disclosures concise and avoid screen takeover or multiple competing open disclosures.
- Carbon progress indicator guidance: prefer short step labels, clear current/complete/not started states, and existing token-based status colors.
- Local product structure: the app currently toggles between Landing and Dashboard rather than using page routing, so a separate orchestration page would add navigation and state complexity.
- Local product structure: the center panel already owns the live reasoning flow, while the right panel owns actions and audit outcomes.

## Chosen Palette

- Reuse current palette and Carbon status colors. No palette change recommended.

## Chosen Typography

- Reuse current typography: IBM Plex Mono with existing dashboard title/body scales. No typography change recommended.

## Design Decisions Log

- 2026-05-03: Recommended same-page orchestration view instead of a separate page because the current app is a single dashboard surface, the center panel already hosts the live analysis narrative, and critical workflow information should remain visible rather than hidden in a secondary destination.
- 2026-05-03: Recommended extending the existing center-panel stack with a dedicated orchestration card beneath Diagnosis and above verification, keeping right-panel actions unchanged.
- 2026-05-03: Recommended reusing existing OpsBob tokens: blue for active/running, amber for pending/review, green for complete/success, red for failed/blocked.

## Export History

- None.