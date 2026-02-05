//! Scheme builder implementations for the x402 facilitator.
//!
//! This module provides [`X402SchemeFacilitatorBuilder`] implementations for all supported
//! payment schemes. These builders create scheme facilitators from the generic
//! [`ChainProvider`] enum by extracting the appropriate
//! chain-specific provider.
//!
//! # Supported Schemes
//!
//! | Scheme | Chains | Description |
//! |--------|--------|-------------|
//! | [`V1Eip155Exact`] | EIP-155 (EVM) | V1 protocol with exact amount on EVM |
//! | [`V2Eip155Exact`] | EIP-155 (EVM) | V2 protocol with exact amount on EVM |
//!
//! # Example
//!
//! ```ignore
//! use x402_types::scheme::{SchemeBlueprints, X402SchemeFacilitatorBuilder};
//! use x402_chain_eip155::V2Eip155Exact;
//! use crate::chain::ChainProvider;
//!
//! // Register schemes
//! let blueprints = SchemeBlueprints::new()
//!     .and_register(V2Eip155Exact)
//!     .and_register(V2Eip155Exact);
//! ```

#[allow(unused_imports)] // For when no chain features are enabled
use crate::chain::ChainProvider;
#[allow(unused_imports)] // For when no chain features are enabled
use std::sync::Arc;
#[allow(unused_imports)] // For when no chain features are enabled
use x402_types::scheme::{X402SchemeFacilitator, X402SchemeFacilitatorBuilder};

#[cfg(feature = "chain-eip155")]
use x402_chain_eip155::{V1Eip155Exact, V2Eip155Exact};
#[cfg(feature = "chain-eip155")]
impl X402SchemeFacilitatorBuilder<&ChainProvider> for V2Eip155Exact {
    fn build(
        &self,
        provider: &ChainProvider,
        config: Option<serde_json::Value>,
    ) -> Result<Box<dyn X402SchemeFacilitator>, Box<dyn std::error::Error>> {
        #[allow(irrefutable_let_patterns)] // For when just chain-eip155 is enabled
        let eip155_provider = if let ChainProvider::Eip155(provider) = provider {
            Arc::clone(provider)
        } else {
            return Err("V2Eip155Exact::build: provider must be an Eip155ChainProvider".into());
        };
        self.build(eip155_provider, config)
    }
}

#[cfg(feature = "chain-eip155")]
impl X402SchemeFacilitatorBuilder<&ChainProvider> for V1Eip155Exact {
    fn build(
        &self,
        provider: &ChainProvider,
        config: Option<serde_json::Value>,
    ) -> Result<Box<dyn X402SchemeFacilitator>, Box<dyn std::error::Error>> {
        #[allow(irrefutable_let_patterns)] // For when just chain-eip155 is enabled
        let eip155_provider = if let ChainProvider::Eip155(provider) = provider {
            Arc::clone(provider)
        } else {
            return Err("V1Eip155Exact::build: provider must be an Eip155ChainProvider".into());
        };
        self.build(eip155_provider, config)
    }
}
