//! V2 EIP-155 "exact" payment scheme implementation.
//!
//! This module implements the "exact" payment scheme for EVM chains using
//! the V2 x402 protocol. It builds on the V1 implementation but uses
//! CAIP-2 chain identifiers instead of network names.
//!
//! # Differences from V1
//!
//! - Uses CAIP-2 chain IDs (e.g., `eip155:42793`) instead of network names
//! - Payment requirements are embedded in the payload for verification
//! - Cleaner separation between accepted requirements and authorization
//!
//! # Features
//!
//! - EIP-712 typed data signing for payment authorization
//! - EIP-6492 support for counterfactual smart wallet signatures
//! - EIP-1271 support for deployed smart wallet signatures
//! - EOA signature support with split (v, r, s) components
//! - On-chain balance verification before settlement
//!
//! # Usage
//!
//! ```ignore
//! use alloy_primitives::address;
//! use x402_chain_eip155::chain::{Eip155ChainReference, Eip155TokenDeployment, TokenDeploymentEip712};
//! use x402_chain_eip155::v2_eip155_exact::V2Eip155Exact;
//!
//! let bbt = Eip155TokenDeployment {
//!     chain_reference: Eip155ChainReference::new(42793),
//!     address: address!("0x7EfE4bdd11237610bcFca478937658bE39F8dfd6"),
//!     decimals: 18,
//!     eip712: Some(TokenDeploymentEip712 {
//!         name: "BBT".into(),
//!         version: "1".into(),
//!     }),
//! };
//! let price = V2Eip155Exact::price_tag(
//!     "0x1234...",  // pay_to address
//!     bbt.amount(10_000_000_000_000_000u64.into()),  // 0.01 BBT
//! );
//! ```

#[cfg(feature = "server")]
pub mod server;
#[cfg(feature = "server")]
#[allow(unused_imports)]
pub use server::*;

#[cfg(feature = "facilitator")]
pub mod facilitator;
#[cfg(feature = "facilitator")]
pub use facilitator::*;

#[cfg(feature = "client")]
pub mod client;
#[cfg(feature = "client")]
pub use client::*;

pub mod types;
pub use types::*;

use x402_types::scheme::X402SchemeId;

pub struct V2Eip155Exact;

impl X402SchemeId for V2Eip155Exact {
    fn namespace(&self) -> &str {
        "eip155"
    }

    fn scheme(&self) -> &str {
        ExactScheme.as_ref()
    }
}
