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
