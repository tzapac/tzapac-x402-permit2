# x402-rs

[![Crates.io](https://img.shields.io/crates/v/x402-types.svg)](https://crates.io/crates/x402-types)
[![Docs.rs](https://docs.rs/x402-types/badge.svg)](https://docs.rs/x402-types)
[![GHCR](https://img.shields.io/badge/ghcr.io-x402--facilitator-blue)](https://github.com/orgs/x402-rs/packages/container/package/x402-facilitator)

> A comprehensive Rust toolkit for the [x402 protocol](https://www.x402.org), enabling blockchain payments directly through HTTP using the native `402 Payment Required` status code.

x402-rs is a modular, production-ready implementation of the x402 protocol with Etherlink (EVM/EIP-155) support and protocol versions (V1 and V2).

### Core Crates

| Crate                                                           | Badges                                                                                                                                                                                                                             | Description                                                                                      |
|-----------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------|
| **[`x402-types`](./crates/x402-types)**                         | [![Crates.io](https://img.shields.io/crates/v/x402-types.svg)](https://crates.io/crates/x402-types) [![Docs.rs](https://docs.rs/x402-types/badge.svg)](https://docs.rs/x402-types)                                                 | Core protocol types, facilitator traits, and utilities. Foundation for all x402 implementations. |
| **[`x402-axum`](./crates/x402-axum)**                           | [![Crates.io](https://img.shields.io/crates/v/x402-axum.svg)](https://crates.io/crates/x402-axum) [![Docs.rs](https://docs.rs/x402-axum/badge.svg)](https://docs.rs/x402-axum)                                                     | Axum middleware for protecting routes with x402 payments.                                        |
| **[`x402-reqwest`](./crates/x402-reqwest)**                     | [![Crates.io](https://img.shields.io/crates/v/x402-reqwest.svg)](https://crates.io/crates/x402-reqwest) [![Docs.rs](https://docs.rs/x402-reqwest/badge.svg)](https://docs.rs/x402-reqwest)                                         | Reqwest middleware for transparent x402 payment handling.                                        |
| **[`x402-facilitator-local`](./crates/x402-facilitator-local)** | [![Crates.io](https://img.shields.io/crates/v/x402-facilitator-local.svg)](https://crates.io/crates/x402-facilitator-local) [![Docs.rs](https://docs.rs/x402-facilitator-local/badge.svg)](https://docs.rs/x402-facilitator-local) | Local facilitator implementation for payment verification and settlement.                        |

### Blockchain Support

| Crate                                                        | Badges                                                                                                                                                                                                         | Description                                               |
|--------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------|
| **[`x402-chain-eip155`](./crates/chains/x402-chain-eip155)** | [![Crates.io](https://img.shields.io/crates/v/x402-chain-eip155.svg)](https://crates.io/crates/x402-chain-eip155) [![Docs.rs](https://docs.rs/x402-chain-eip155/badge.svg)](https://docs.rs/x402-chain-eip155) | EVM/EIP-155 chain support (Etherlink). |

### Deployment

| Crate                                   | Description                                                             |
|-----------------------------------------|-------------------------------------------------------------------------|
| **[`x402-facilitator`](./facilitator)** | Production-ready facilitator server binary (not published to crates.io) |

## About x402

The [x402 protocol](https://www.x402.org) is a proposed standard for making blockchain payments directly through HTTP using the native `402 Payment Required` status code.

**How it works:**
1. **Server** declares payment requirements for specific routes
2. **Client** sends cryptographically signed payment payloads
3. **Facilitator** verifies and settles payments on-chain

This enables seamless pay-per-use transactions without requiring clients to manage blockchain interactions directly.

## Quick Start

### Protect Routes (Server)

Use `x402-axum` to gate your routes behind on-chain payments:

```rust
use alloy_primitives::address;
use axum::{Router, routing::get};
use x402_axum::X402Middleware;
use x402_chain_eip155::V2Eip155Exact;
use x402_chain_eip155::chain::{Eip155ChainReference, Eip155TokenDeployment, TokenDeploymentEip712};

let x402 = X402Middleware::new("http://facilitator.example.com");

let bbt = Eip155TokenDeployment {
    chain_reference: Eip155ChainReference::new(42793),
    address: address!("0x7EfE4bdd11237610bcFca478937658bE39F8dfd6"),
    decimals: 18,
    eip712: Some(TokenDeploymentEip712 {
        name: "BBT".into(),
        version: "1".into(),
    }),
};

let app = Router::new().route(
    "/paid-content",
    get(handler).layer(
        x402.with_price_tag(V2Eip155Exact::price_tag(
            address!("0xYourAddress"),
            bbt.amount(10u64),
        ))
    ),
);
```

See [`x402-axum` documentation](./crates/x402-axum/README.md) for more details.

### Send Payments (Client)

Use `x402-reqwest` to automatically handle x402 payments:

```rust
use x402_reqwest::{ReqwestWithPayments, ReqwestWithPaymentsBuild, X402Client};
use x402_chain_eip155::V2Eip155ExactClient;
use alloy_signer_local::PrivateKeySigner;
use std::sync::Arc;
use reqwest::Client;

let signer: Arc<PrivateKeySigner> = Arc::new("0x...".parse()?);

let x402_client = X402Client::new()
    .register(V2Eip155ExactClient::new(signer));

let client = Client::new()
    .with_payments(x402_client)
    .build();

let res = client
    .get("https://example.com/protected")
    .send()
    .await?;
```

See [`x402-reqwest` documentation](./crates/x402-reqwest/README.md) for more details.

## Run a Facilitator

### Docker

Prebuilt Docker images are available at [GitHub Container Registry](https://github.com/orgs/x402-rs/packages/container/package/x402-facilitator):

```shell
docker run -v $(pwd)/config.json:/app/config.json -p 9090:9090 ghcr.io/x402-rs/x402-facilitator
```

### Etherlink PoC Runtime Notes (This Repo)

For this repository's Etherlink PoC stack, facilitator runtime is wired via
`Dockerfile.bbt` / compose and requires explicit proxy configuration:

- `X402_EXACT_PERMIT2_PROXY_ADDRESS=0xB6FD384A0626BfeF85f3dBaf5223Dd964684B09E`
- `X402_EXACT_PERMIT2_PROXY_CODEHASH_ALLOWLIST=0x73020ff18bfd4eaba45de17760ad433063ed6267a8371ef54a39083a14180366`

The PoC composes this as:

```shell
docker compose -f docker-compose.model3-etherlink.yml up -d --build
```

### Build Your Own

For custom facilitator implementations, see the [Build Your Own Facilitator](./docs/build-your-own-facilitator.md) guide.

For full facilitator configuration and deployment details, see the [`x402-facilitator` README](./facilitator/README.md).

## Roadmap

| Milestone                           | Description                                                                                              |   Status   |
|:------------------------------------|:---------------------------------------------------------------------------------------------------------|:----------:|
| Facilitator for Etherlink (BBT)     | Payment verification and settlement service, enabling real-time pay-per-use transactions for Etherlink.  | ✅ Complete |
| Metrics and Tracing                 | Expose OpenTelemetry metrics and structured tracing for observability, monitoring, and debugging         | ✅ Complete |
| Server Middleware                   | Provide ready-to-use integration for Rust web frameworks such as axum and tower.                         | ✅ Complete |
| Client Library                      | Provide a lightweight Rust library for initiating and managing x402 payment flows from Rust clients.     | ✅ Complete |
| Protocol v2 Support                 | Support x402 protocol version 2 with improved payload structure.                                         | ✅ Complete |
| Etherlink-only build                | Limit to Etherlink (EVM/EIP-155) for focused deployment.                                                  | ✅ Complete |
| Axum Middleware v2 Support          | Full x402 protocol v2 support in x402-axum.                                                               | ✅ Complete |
| Reqwest Client v2 Support           | Full x402 protocol v2 support in x402-reqwest.                                                            | ✅ Complete |
| Build your own facilitator hooks    | Pre/post hooks for analytics, access control, and auditability.                                          | 🔜 Planned |
| Bazaar Extension                    | Marketplace integration for discovering and purchasing x402-protected resources.                         | 🔜 Planned |
| Gasless Approval Flow               | Support for Permit2 and ERC20 approvals to enable gasless payment authorization.                         | 🔜 Planned |
| Upto Scheme                         | Payment scheme supporting "up to" amount payments with flexible pricing.                                 | 🔜 Planned |
| Deferred Scheme                     | Payment scheme supporting deferred settlement and payment scheduling.                                    | 🔜 Planned |

## Related Resources

* [x402 Protocol Documentation](https://x402.org)
* [x402 Overview by Coinbase](https://docs.cdp.coinbase.com/x402/docs/overview)
* [Facilitator Documentation by Coinbase](https://docs.cdp.coinbase.com/x402/docs/facilitator)

## Contributions and Feedback

Feel free to open issues or pull requests to improve x402 support in the Rust ecosystem.

## License

[Apache-2.0](LICENSE)
