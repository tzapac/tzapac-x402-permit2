# Ralph Audit Loop (OpenAI Codex) - x402 / Etherlink

This folder wires up a long-lived, autonomous, **read-only** audit loop for this repo using the **OpenAI Codex CLI**.

The agent documents findings to markdown reports, but **must not modify** the codebase.

## What This Repo Is

This repo is a Coinbase-aligned x402 facilitator + store PoC for **Etherlink** using:

- x402 **v2** transport headers (`Payment-Required`, `Payment-Signature`)
- Permit2 **SignatureTransfer** witness flow (spender is an x402 Permit2 proxy)
- Facilitator-sponsored gas (facilitator submits the settlement transaction)

Because this is crypto-adjacent and touches payment flows, treat audits as high-risk operations.

## Prereqs

- `codex` CLI on your PATH and authenticated
- `jq` (the runner uses it to read/update `prd.json`)
- Bash

## How To Run

From repo root:

```bash
cd .codex/ralph-audit
./ralph.sh 20
```

Web research is enabled by default. To disable:

```bash
./ralph.sh 20 --no-search
```

## Logs

- High-level progress: `events.log`
- Full Codex output: `run.log`

```bash
tail -n 200 -f events.log
tail -n 200 -f run.log
```

## Output

Audit reports are written under:

- `.codex/ralph-audit/audit/*.md`

The exact filenames come from each story's acceptance criteria in `prd.json`.

## Customize

- Edit `prd.json` to match the audits you care about.
- Edit `CODEX.md` to match your quality bar and safety rules.
- Edit the model pin in `ralph.sh` (`REQUESTED_MODEL`, `REASONING_EFFORT`).

