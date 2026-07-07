## 2026-02-25 Architectural Direction
- Keep backend as mock data; prioritize employee-facing visibility and triage workflows.
- Upgrade global pages with filtering, summaries, and actionable states first.
- Avoid introducing new dependencies; follow existing Element Plus + VXE patterns.

## 2026-02-25 UX/Product Decisions
- Employee concern priority is modeled explicitly: current requirement progress + pending bug pressure + P0 risk.
- Global pages remain list-centric but move from passive display to operational triage with quick filters.
- P0 zone focuses on stage-based split (testing vs post-release) to support different escalation paths.

## 2026-02-25 Consolidation Decisions
- Navigation is simplified to one visible menu entry for 需求与缺陷; Bug/P0 routes remain as hidden compatibility routes mapped to the same page.
- The unified page is treated as operations console: summary stats + tab switching + inline status actions + project deep-link.
- Project alignment is prioritized over legacy static list shape so all critical actions operate on workflow-origin data.
