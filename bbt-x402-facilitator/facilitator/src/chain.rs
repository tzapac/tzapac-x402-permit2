//! Blockchain-specific types and providers for x402 payment processing.
//!
//! This module provides abstractions for interacting with different blockchain networks
//! in the x402 protocol. It supports multiple blockchain families:
//!
//! - **EIP-155 (EVM)**: Etherlink
//!
//! # Architecture
//!
//! The module is organized around the concept of chain providers and chain identifiers:
//!
//! - [`ChainId`] - A CAIP-2 compliant chain identifier (e.g., `eip155:42793` for Etherlink)
//! - [`ChainProvider`] - Enum wrapping chain-specific providers
//! - [`ChainRegistry`] - Registry of configured chain providers
//!
//! # Example
//!
//! ```ignore
//! use x402_types::chain::{ChainId, ChainIdPattern};
//!
//! // Create a specific chain ID
//! let etherlink = ChainId::new("eip155", "42793");
//!
//! // Create a pattern that matches all EVM chains
//! let all_evm = ChainIdPattern::wildcard("eip155");
//! assert!(all_evm.matches(&etherlink));
//!
//! // Create a pattern for specific chains
//! let mainnet_chains = ChainIdPattern::set("eip155", ["42793"].into_iter().map(String::from).collect());
//! assert!(mainnet_chains.matches(&etherlink));
//! ```

use std::collections::HashMap;
#[cfg(any(
    feature = "chain-eip155"
))]
use std::sync::Arc;
#[cfg(feature = "chain-eip155")]
use x402_chain_eip155::chain as eip155;
use x402_types::chain::{ChainId, ChainProviderOps, ChainRegistry, FromConfig};

use crate::config::{ChainConfig, ChainsConfig};

/// A blockchain provider that can interact with EVM chains.
///
/// This enum wraps chain-specific providers and provides a unified interface
/// for the facilitator to interact with different blockchain networks.
///
/// # Variants
///
/// - `Eip155` - Provider for EVM-compatible chains (Etherlink)
#[derive(Debug, Clone)]
pub enum ChainProvider {
    /// EVM chain provider for EIP-155 compatible networks.
    #[cfg(feature = "chain-eip155")]
    Eip155(Arc<eip155::Eip155ChainProvider>),
}

/// Creates a new chain provider from configuration.
///
/// This factory method inspects the configuration type and creates the appropriate
/// chain-specific provider (EVM).
///
/// # Errors
///
/// Returns an error if:
/// - RPC connection fails
/// - Signer configuration is invalid
/// - Required configuration is missing
#[async_trait::async_trait]
impl FromConfig<ChainConfig> for ChainProvider {
    async fn from_config(chains: &ChainConfig) -> Result<Self, Box<dyn std::error::Error>> {
        #[allow(unused_variables)] // For when no chain features enabled
        let provider = match chains {
            #[cfg(feature = "chain-eip155")]
            ChainConfig::Eip155(config) => {
                let provider = eip155::Eip155ChainProvider::from_config(config).await?;
                ChainProvider::Eip155(Arc::new(provider))
            }
            #[allow(unreachable_patterns)] // For when no chain features enabled
            _ => unreachable!("ChainConfig variant not enabled in this build"),
        };
        #[allow(unreachable_code)] // For when no chain features enabled
        Ok(provider)
    }
}

impl ChainProviderOps for ChainProvider {
    fn signer_addresses(&self) -> Vec<String> {
        match self {
            #[cfg(feature = "chain-eip155")]
            ChainProvider::Eip155(provider) => provider.signer_addresses(),
            #[allow(unreachable_patterns)] // For when no chain features enabled
            _ => unreachable!("ChainProvider variant not enabled in this build"),
        }
    }

    fn chain_id(&self) -> ChainId {
        match self {
            #[cfg(feature = "chain-eip155")]
            ChainProvider::Eip155(provider) => provider.chain_id(),
            #[allow(unreachable_patterns)] // For when no chain features enabled
            _ => unreachable!("ChainProvider variant not enabled in this build"),
        }
    }
}

/// Creates a new chain registry from configuration.
///
/// Initializes providers for all configured chains. Each chain configuration
/// is processed and a corresponding provider is created and stored.
///
/// # Errors
///
/// Returns an error if any chain provider fails to initialize.
#[async_trait::async_trait]
impl FromConfig<ChainsConfig> for ChainRegistry<ChainProvider> {
    async fn from_config(chains: &ChainsConfig) -> Result<Self, Box<dyn std::error::Error>> {
        let mut providers = HashMap::new();
        for chain in chains.iter() {
            let chain_provider = ChainProvider::from_config(chain).await?;
            providers.insert(chain_provider.chain_id(), chain_provider);
        }
        Ok(Self::new(providers))
    }
}
