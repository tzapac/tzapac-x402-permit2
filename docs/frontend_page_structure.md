# Frontend Page Structure (x402 Permit2 Uplink)

This document maps the public page layout, functional IDs, and role-based behavior in `wallet_connect_poc.html` and `wallet_connect_poc.js`.

## Section Hierarchy

1. `Overview` tab
- Role selector (`client`, `store`, `facilitator`)
- Flow explanation (architecture + sequence)
- Trust/credibility block (chain/spec/addresses + copy actions)
- Navigation CTAs to Demo/Integration/Setup

2. `Demo` tab
- Step 1: Connect Wallet
- Step 2: Check Facilitator Health
- Step 3: Fetch Payment Requirement
- Step 4: Approve Permit2
- Step 5: Sign & Pay
- Console log stream

3. `Integration Guide` tab
- Client / Store / Facilitator responsibilities
- Role-targeted implementation checklist snippets

4. `Setup Instructions` tab
- Collapsible operational sections:
  - Docker compose
  - `.env` example
  - `.env.multitest` example
  - Facilitator config JSON
  - Build/run commands

5. `Docs` tab
- Links to repository docs and guides

6. `Terms & Privacy` tab
- Terms text and return-to-demo action

## Core UX Controls

- Tab buttons: `.tab-button[data-tab]`
- Tab panels: `.tab-panel[data-panel]`
- Role buttons: `.role-button[data-role]`
- Role panels: `[data-role-panel]`
- Role checklists: `[data-role-checklist]`

## Demo Flow IDs

- Step statuses: `step-status-1` ... `step-status-5`
- Connect: `connect-btn`
- Facilitator health: `health-btn`
- Get payment: `requirements-btn`
- Approve Permit2: `approve-btn`
- Sign & pay: `pay-btn`

## Request/Response Preview IDs

- Health response preview: `health-response`
- Payment requirement preview: `requirements-response`
- Settlement response preview: `settle-response`

## Trust Metadata IDs

- Permit2 address: `address-permit2`
- x402 proxy address: `address-x402-proxy`
- Token address: `address-token`
- Facilitator URL: `address-facilitator`
- Store URL: `address-store`

## Copy Buttons

- Copy action buttons use class `.copy-btn` with `data-copy-target` pointing to the source element ID.

## Persisted Browser State

- Role selection: `localStorage["tzapac_x402_role"]`
- Usage notice acknowledgement (24h TTL): `localStorage["tzapac_x402_disclaimer_ack_at"]`

## Notes for Future Changes

- Keep existing functional IDs stable unless JS is updated in lockstep.
- Preserve `Payment-Signature` flow and step ordering for integrator consistency.
- If new roles are added, update:
  - role button set
  - `ROLE_DESCRIPTIONS`
  - role panel and checklist selectors
