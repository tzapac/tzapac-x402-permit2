#![cfg_attr(docsrs, feature(doc_auto_cfg))]

//! Local facilitator implementation for the x402 payment protocol.
//!
//! This crate provides [`FacilitatorLocal`], a [`Facilitator`](x402_types::facilitator::Facilitator)
//! implementation that validates x402 payment payloads and performs on-chain settlements
//! using registered scheme handlers.
//!
//! This crate provides:
//! - route-level error handling via Axum handlers
//! - request-level compliance screening
//! - chain and scheme orchestration with an internal registry

pub mod compliance;
pub mod facilitator_local;
pub mod handlers;
pub mod util;

pub use compliance::*;
pub use facilitator_local::*;
pub use handlers::*;
