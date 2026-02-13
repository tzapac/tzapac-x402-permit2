//! x402 Facilitator HTTP server entrypoint.
//!
//! This module initializes and runs the Axum-based HTTP server that exposes the x402 protocol
//! interface for payment verification and settlement across multiple blockchain networks.
//!
//! # Endpoints
//!
//! | Method | Path | Description |
//! |--------|------|-------------|
//! | `GET` | `/verify` | Get supported verification schema |
//! | `POST` | `/verify` | Verify a payment payload against requirements |
//! | `GET` | `/settle` | Get supported settlement schema |
//! | `POST` | `/settle` | Settle an accepted payment payload on-chain |
//! | `GET` | `/supported` | List supported payment kinds (version/scheme/network) |
//! | `GET` | `/health` | Health check endpoint |
//!
//! # Features
//!
//! - `Multi-chain support`: EIP-155 (EVM) networks
//! - `OpenTelemetry` tracing (with `telemetry` feature): distributed tracing and metrics
//! - `CORS` support: Cross-origin requests for browser-based clients
//! - `Graceful shutdown`: Signal-based shutdown with cleanup
//!
//! # Environment Variables
//!
//! - `HOST` - Server bind address (default: `0.0.0.0`)
//! - `PORT` - Server port (default: `9090`)
//! - `CONFIG` - Path to configuration file (default: `config.json`)
//! - `X402_CORS_ALLOWED_ORIGINS` - comma-separated CORS allowlist, or `*` to allow all
//! - COMPLIANCE_SCREENING_ENABLED - enable off-chain compliance checks (true/false, defaults to true)
//! - `COMPLIANCE_DENY_LIST` - comma-separated list of denied addresses
//! - `COMPLIANCE_ALLOW_LIST` - comma-separated list of allowed addresses (if set, only these are allowed)
//! - `OTEL_*` - OpenTelemetry configuration (when `telemetry` feature enabled)

use std::io;
use std::net::SocketAddr;

use axum::http::{HeaderValue, Method};
use axum::Router;
use dotenvy::dotenv;
use tower_http::cors;

use x402_facilitator_local::util::SigDown;
use x402_facilitator_local::{FacilitatorLocal, handlers};
#[cfg(feature = "chain-eip155")]
use x402_chain_eip155::{V1Eip155Exact, V2Eip155Exact};
use x402_types::chain::{ChainRegistry, FromConfig};
use x402_types::scheme::{SchemeBlueprints, SchemeRegistry};
#[cfg(feature = "telemetry")]
use x402_facilitator_local::util::Telemetry;

use crate::config::Config;

fn build_cors_layer() -> Result<cors::CorsLayer, io::Error> {
    let raw = std::env::var("X402_CORS_ALLOWED_ORIGINS").unwrap_or_else(|_| {
        "http://localhost:9091,http://127.0.0.1:9091,https://exp-store.bubbletez.com"
            .to_string()
    });

    let base = cors::CorsLayer::new()
        .allow_methods([Method::GET, Method::POST, Method::OPTIONS])
        .allow_headers(cors::Any);

    if raw.trim() == "*" {
        return Ok(base.allow_origin(cors::Any));
    }

    let origins: Vec<HeaderValue> = raw
        .split(",")
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .map(HeaderValue::from_str)
        .collect::<Result<Vec<_>, _>>()
        .map_err(|e| {
            io::Error::new(
                io::ErrorKind::InvalidInput,
                format!("invalid X402_CORS_ALLOWED_ORIGINS: {e}"),
            )
        })?;

    if origins.is_empty() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "X402_CORS_ALLOWED_ORIGINS is empty",
        ));
    }

    Ok(base.allow_origin(origins))
}

fn load_compliance_gate() -> Result<x402_facilitator_local::compliance::ComplianceGate, io::Error> {
    x402_facilitator_local::compliance::ComplianceGate::from_env()
        .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, e))
}

/// Initializes the x402 facilitator server.
///
/// - Loads `.env` variables.
/// - Initializes OpenTelemetry tracing.
/// - Connects to Ethereum providers for supported networks.
/// - Starts an Axum HTTP server with the x402 protocol handlers.
///
/// Binds to the address specified by the `HOST` and `PORT` env vars.
pub async fn run() -> Result<(), Box<dyn std::error::Error>> {
    rustls::crypto::CryptoProvider::install_default(rustls::crypto::ring::default_provider())
        .map_err(|e| io::Error::new(io::ErrorKind::Other, format!("failed to initialize rustls crypto provider: {e:?}")))?;

    // Load .env variables
    dotenv().ok();

    #[cfg(feature = "telemetry")]
    let telemetry_layer = {
        let telemetry = Telemetry::new()
            .with_name(env!("CARGO_PKG_NAME"))
            .with_version(env!("CARGO_PKG_VERSION"))
            .register();
        telemetry.http_tracing()
    };

    let config = Config::load()?;
    let compliance_gate = load_compliance_gate()?;

    let chain_registry = ChainRegistry::from_config(config.chains()).await?;
    let scheme_blueprints = {
        #[allow(unused_mut)] // For when no chain features are enabled
        let mut scheme_blueprints = SchemeBlueprints::new();
        #[cfg(feature = "chain-eip155")]
        {
            scheme_blueprints.register(V1Eip155Exact);
            scheme_blueprints.register(V2Eip155Exact);
        }
        scheme_blueprints
    };
    let scheme_registry =
        SchemeRegistry::build(chain_registry, scheme_blueprints, config.schemes());

    let facilitator = FacilitatorLocal::new_with_compliance(scheme_registry, compliance_gate);
    let axum_state = std::sync::Arc::new(facilitator);

    let mut http_endpoints = Router::new().merge(handlers::routes().with_state(axum_state));
    #[cfg(feature = "telemetry")]
    {
        http_endpoints = http_endpoints.layer(telemetry_layer);
    }
    let http_endpoints = http_endpoints.layer(build_cors_layer()?);

    let addr = SocketAddr::new(config.host(), config.port());
    #[cfg(feature = "telemetry")]
    tracing::info!("Starting server at http://{}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await;
    #[cfg(feature = "telemetry")]
    let listener = listener.inspect_err(|e| tracing::error!("Failed to bind to {}: {}", addr, e));
    let listener = listener?;

    let sig_down = SigDown::try_new()?;
    let axum_cancellation_token = sig_down.cancellation_token();
    let axum_graceful_shutdown = async move { axum_cancellation_token.cancelled().await };
    axum::serve(listener, http_endpoints)
        .with_graceful_shutdown(axum_graceful_shutdown)
        .await?;

    Ok(())
}
