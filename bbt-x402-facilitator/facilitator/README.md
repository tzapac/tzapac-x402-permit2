# x402-facilitator

A production-ready x402 facilitator server binary.

This crate provides a complete, runnable HTTP server that implements the [x402](https://www.x402.org) payment protocol. It supports EVM/EIP-155 networks and can verify and settle payments on-chain.

The crate can also be used as a library to build custom facilitator implementations.

## Features

- **Multi-chain Support**: EVM (EIP-155) blockchains
- **Multiple Payment Schemes**: V1 and V2 protocol implementations
- **OpenTelemetry Integration**: Optional distributed tracing and metrics (`telemetry` feature)
- **Graceful Shutdown**: Clean shutdown on SIGTERM/SIGINT signals
- **CORS Support**: Cross-origin requests enabled for web clients
- **Flexible Configuration**: JSON-based configuration with environment variable overrides
- **Modular Chain Support**: Enable only the blockchain networks you need via feature flags

## Installation

### As a Binary (via cargo install)

```bash
# Install from git
cargo install --git https://github.com/x402-rs/x402-rs --package x402-facilitator

# Run the installed binary
x402-facilitator --config /path/to/config.json # Or provide config path via $CONF env var
```

### As a Library

Add to your `Cargo.toml`:

```toml
[dependencies]
x402-facilitator = { git = "https://github.com/x402-rs/x402-rs" }
```


## Usage

### Running the Server

```bash
# Build and run from source
cargo run --package x402-facilitator

# With telemetry
cargo run --package x402-facilitator --features telemetry

# With specific chains only
cargo run --package x402-facilitator --features chain-eip155

# With the full feature (all chains + telemetry)
cargo run --package x402-facilitator --features full

# Specify custom config file
cargo run --package x402-facilitator -- --config /path/to/config.json
```

### Configuration

Create a `config.json` file:

```json
{
  "port": 9090,
  "host": "0.0.0.0",
  "chains": {
    "eip155:8453": {
      "eip1559": true,
      "signers": ["$FACILITATOR_PRIVATE_KEY"],
      "rpc": [
        {
          "http": "https://mainnet.base.org",
          "rate_limit": 100
        }
      ]
    }
  },
  "schemes": [
    {
      "scheme": "v2-eip155-exact",
      "chains": ["eip155:8453"]
    }
  ]
}
```

### Environment Variables

| Variable                      | Description                      | Default       |
|-------------------------------|----------------------------------|---------------|
| `HOST`                        | Server bind address              | `0.0.0.0`     |
| `PORT`                        | Server port                      | `9090`        |
| `CONFIG`                      | Path to config file              | `config.json` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OpenTelemetry collector endpoint | -             |
| `OTEL_SERVICE_NAME`           | Service name for traces          | -             |

## HTTP Endpoints

| Endpoint     | Method | Description             |
|--------------|--------|-------------------------|
| `/`          | GET    | Server greeting         |
| `/verify`    | GET    | Schema information      |
| `/verify`    | POST   | Verify payment payload  |
| `/settle`    | GET    | Schema information      |
| `/settle`    | POST   | Settle payment on-chain |
| `/supported` | GET    | List supported schemes  |
| `/health`    | GET    | Health check            |

## Architecture

The facilitator is built on top of the `x402-facilitator-local` crate and uses:

- **Axum**: HTTP server framework
- **Tokio**: Async runtime
- **x402-types**: Core protocol types and configuration (via `x402_types::config`)
- **x402-chain-\\\\*\\\**: Chain-specific implementations

```text
┌─────────────┐
│   Axum HTTP │
│   Server    │
└──────┬──────┘
       │
┌──────▼──────┐
│ Facilitator │
│   Local     │
└──────┬──────┘
       │
┌──────▼──────┐
│   Scheme    │
│  Registry   │
└──────┬──────┘
       │
  ┌────┴────┐
  ▼         ▼
┌─────┐
│EIP  │
│155  │
└─────┘
```

## Feature Flags

| Feature        | Description                                   |
|----------------|-----------------------------------------------|
| `telemetry`    | Enable OpenTelemetry tracing and metrics      |
| `chain-eip155` | Enable EVM/EIP-155 chain support              |
| `full`         | Enable all features: telemetry + EIP-155      |


## License

Apache-2.0
