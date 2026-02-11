# Deployment Information

## Proxy Initialization Risk (Important)

The x402 Permit2 proxy uses a one-time initializer pattern:

- `initialize(address _permit2)` is `external` and can be called exactly once.
- If deployment and initialization are separated, there is a race window where another party can call `initialize` first.
- If that happens, the proxy can be permanently pointed at the wrong Permit2 address and become unusable or unsafe for settlement.

### Why This Matters

This is a deployment-time risk, not a runtime bug after proper initialization.
Once initialized, the proxy cannot be re-initialized.

### Required Deployment Practice

Use atomic deploy+initialize for any new proxy deployment.

- Recommended: deploy via `x402ExactPermit2ProxyFactory` so initialization happens in the same transaction context.
- Avoid two-step manual flows (`deploy` first, `initialize` later).

### Post-Deployment Checks

After deployment, verify all of the following:

1. Proxy bytecode matches expected x402 proxy bytecode.
2. `PERMIT2` points to the canonical Permit2 contract for that chain.
3. Proxy is already initialized (and cannot be re-initialized).
4. Facilitator is configured with the expected proxy address.
5. Facilitator proxy codehash allowlist is set (`X402_EXACT_PERMIT2_PROXY_CODEHASH_ALLOWLIST`) for runtime pinning.

### Current Etherlink Status

For this project’s deployed Etherlink proxy, initialization has already been completed and verified.
The initialization race concern applies to future deployments if atomic deploy+initialize is not used.

## Deferred / Accepted Items (No-Redeploy Decision)

To avoid introducing new contract ownership risk, we are **not** redeploying the proxy for low-severity contract-level enhancements at this stage.

Deferred items:

1. Event enrichment (`Settled` / `SettledWithPermit` with indexed fields).
2. Additional witness type-string guardrails beyond current runtime checks.

Reason:

- Both items are improvements, not blockers for the current Coinbase-aligned Permit2 witness flow.
- Implementing item 1 requires contract changes and redeployment.
- We prefer to avoid replacing the currently verified, Coinbase-equivalent proxy code path unless Coinbase deploys an official Etherlink proxy.

Responsibility boundary (important):

- The deployed Etherlink proxy address `0xB6FD384A0626BfeF85f3dBaf5223Dd964684B09E` is operator-deployed in this project.
- Even with exact source/bytecode equivalence to Coinbase’s implementation, operational responsibility remains with this deployment/operator until Coinbase deploys and operates their own Etherlink proxy.
