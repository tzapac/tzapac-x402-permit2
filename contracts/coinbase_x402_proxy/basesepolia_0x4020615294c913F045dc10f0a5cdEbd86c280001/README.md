# Coinbase x402 Permit2 Proxy (Base Sepolia Verified Source)

- Address: 0x4020615294c913F045dc10f0a5cdEbd86c280001
- Explorer: https://sepolia.basescan.org/address/0x4020615294c913F045dc10f0a5cdEbd86c280001#code
- Extracted: 2026-02-10 02:33:50 UTC

Files extracted from BaseScan's verified 'Standard JSON-Input' listing.

## Deployment Safety Note

`x402BasePermit2Proxy.initialize(address)` is one-time but externally callable.
To avoid deploy/init race conditions on fresh deployments, use
`x402ExactPermit2ProxyFactory.sol` so deploy + initialize happen in a single transaction.
