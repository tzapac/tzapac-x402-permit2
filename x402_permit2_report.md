# x402 Permit2 Report (Etherlink)

## Summary
- Facilitator accepted x402 v2 exact scheme and settled a Permit2 transfer.
- On-chain transaction succeeded for 0.01 BBT.
- Remaining issue: server response parsing (not settlement).

## Transaction
- Tx hash: `0xd33f139dce4ec8666756f5aafa061605f5e1041aae7c99809af3f9432b36d04a`
- Method: `Permit2.transferFrom`
- Amount: `0.01 BBT`
- From/To: `0x3E3f637E2C052AD29558684B85a56D8Ee1334Db9`

## Facilitator Logs (ub1)
```
2026-02-02T10:22:29.149808Z INFO x402_facilitator_local::util::telemetry: OpenTelemetry is not enabled
2026-02-02T10:22:29.150112Z INFO x402_chain_eip155::chain::provider: Using HTTP transport chain=eip155:42793 rpc_url=https://rpc.bubbletez.com/ rate_limit=Some(50)
2026-02-02T10:22:29.165751Z INFO x402_chain_eip155::chain::provider: Using EVM provider chain=eip155:42793 signers=[0x3e3f637e2c052ad29558684b85a56d8ee1334db9]
2026-02-02T10:22:29.165778Z INFO x402_types::scheme: Registered scheme handler chain_id=eip155:42793 scheme=exact id="v1-eip155-exact"
2026-02-02T10:22:29.165787Z INFO x402_types::scheme: Registered scheme handler chain_id=eip155:42793 scheme=exact id="v2-eip155-exact"
2026-02-02T10:22:29.165848Z INFO x402_facilitator::run: Starting server at http://0.0.0.0:9090
2026-02-02T10:23:02.069180Z INFO http_request{otel.kind="server" otel.name=GET /supported method=GET uri=/supported version=HTTP/1.1}: x402_facilitator_local::util::telemetry: status=200 elapsed=0ms
2026-02-02T10:23:59.610408Z INFO http_request{otel.kind="server" otel.name=POST /settle method=POST uri=/settle version=HTTP/1.1}: x402_facilitator_local::util::telemetry: status=200 elapsed=14520ms
2026-02-02T10:24:47.096344Z INFO http_request{otel.kind="server" otel.name=POST /settle method=POST uri=/settle version=HTTP/1.1}: x402_facilitator_local::util::telemetry: status=200 elapsed=14478ms
```

## Server Log Excerpt (x402 flow)
```
Received payment: { ... x402Version:2, scheme:exact, network:eip155:42793, payload.permit2 ... }
Calling facilitator /settle: http://100.112.150.8:9090/settle
Settle request: { x402Version:2, paymentPayload:{...accepted:{scheme:exact, network:eip155:42793, amount:10000000000000000, payTo:0x3E3f..., asset:0x7EfE...}}, paymentRequirements:{...} }
Facilitator response (200): {"success": true, "payer": "0x3E3f...", "transaction": "0xd33f139dce4ec8666756f5aafa061605f5e1041aae7c99809af3f9432b36d04a", "network": "eip155:42793"}
```

## Evidence of x402 Protocol Usage
- `X-PAYMENT-REQUIRED` header returned (x402 v2, scheme exact, network eip155:42793).
- Client generated Permit2 payment payload.
- Server sent `/settle` to facilitator with `paymentPayload.accepted` + `paymentRequirements`.
- Facilitator returned success with transaction hash.

## Notes
- The settlement is confirmed on-chain; any remaining errors are in server response parsing.
