//! EVM chain support for x402 payments via EIP-155.
//!
//! This module provides types and providers for interacting with EVM-compatible blockchains
//! in the x402 protocol. It supports ERC-3009 `transferWithAuthorization` for gasless
//! token transfers, which is the foundation of x402 payments on EVM chains.
//!
//! # Key Types
//!
//! - [`Eip155ChainReference`] - A numeric chain ID for EVM networks (e.g., `42793` for Etherlink)
//! - [`Eip155ChainProvider`] - Provider for interacting with EVM chains
//! - [`Eip155TokenDeployment`] - Token deployment information including address and decimals
//! - [`MetaTransaction`] - Parameters for sending meta-transactions
//!
//! # Submodules
//!
//! - [`types`] - Wire format types like [`ChecksummedAddress`](types::ChecksummedAddress) and [`TokenAmount`](types::TokenAmount)
//! - [`pending_nonce_manager`] - Nonce management for concurrent transaction submission
//!
//! # ERC-3009 Support
//!
//! The x402 protocol uses ERC-3009 `transferWithAuthorization` for payments. This allows
//! users to sign payment authorizations off-chain, which the facilitator then submits
//! on-chain. The facilitator pays the gas fees and is reimbursed through the payment.
//!
//! # Example
//!
//! ```ignore
//! use x402_chain_eip155::chain::{Eip155ChainReference, Eip155TokenDeployment, TokenDeploymentEip712};
//! use alloy_primitives::{address, U256};
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
//!
//! let amount = bbt.parse("0.01").unwrap();
//! // amount.amount is now 10_000_000_000_000_000 (0.01 * 10^18)
//! assert_eq!(amount.amount, U256::from(10_000_000_000_000_000u64));
//! ```

pub mod types;

#[cfg(feature = "facilitator")]
pub mod config;
#[cfg(feature = "facilitator")]
pub mod pending_nonce_manager;
#[cfg(feature = "facilitator")]
pub mod provider;

#[cfg(feature = "facilitator")]
pub use pending_nonce_manager::*;
#[cfg(feature = "facilitator")]
pub use provider::*;

pub use types::*;
