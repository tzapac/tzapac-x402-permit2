//! Server-side price tag generation for V2 EIP-155 exact scheme.
//!
//! This module provides functionality for servers to create V2 price tags
//! that clients can use to generate payment authorizations. V2 uses CAIP-2
//! chain IDs instead of network names.

use alloy_primitives::U256;
use x402_types::chain::{ChainId, DeployedTokenAmount};
use x402_types::proto::v2;

use crate::V2Eip155Exact;
use crate::chain::{ChecksummedAddress, Eip155TokenDeployment};
use crate::v1_eip155_exact::ExactScheme;

impl V2Eip155Exact {
    /// Creates a V2 price tag for an ERC-3009 payment on an EVM chain.
    ///
    /// This function generates a V2 price tag that specifies the payment requirements
    /// for a resource. Unlike V1, V2 uses CAIP-2 chain IDs (e.g., `eip155:42793`) instead
    /// of network names, and embeds the requirements directly in the price tag.
    ///
    /// # Parameters
    ///
    /// - `pay_to`: The recipient address (can be any type convertible to [`ChecksummedAddress`])
    /// - `asset`: The token deployment and amount required
    ///
    /// # Returns
    ///
    /// A [`v2::PriceTag`] that can be included in a `PaymentRequired` response.
    ///
    /// # Example
    ///
    /// ```ignore
    /// use alloy_primitives::address;
    /// use x402_chain_eip155::chain::{Eip155ChainReference, Eip155TokenDeployment, TokenDeploymentEip712};
    /// use x402_chain_eip155::V2Eip155Exact;
    ///
    /// let bbt = Eip155TokenDeployment {
    ///     chain_reference: Eip155ChainReference::new(42793),
    ///     address: address!("0x7EfE4bdd11237610bcFca478937658bE39F8dfd6"),
    ///     decimals: 18,
    ///     eip712: Some(TokenDeploymentEip712 {
    ///         name: "BBT".into(),
    ///         version: "1".into(),
    ///     }),
    /// };
    /// let price_tag = V2Eip155Exact::price_tag(
    ///     "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
    ///     bbt.amount(10_000_000_000_000_000u64), // 0.01 BBT (18 decimals)
    /// );
    /// ```
    #[allow(dead_code)] // Public for consumption by downstream crates.
    pub fn price_tag<A: Into<ChecksummedAddress>>(
        pay_to: A,
        asset: DeployedTokenAmount<U256, Eip155TokenDeployment>,
    ) -> v2::PriceTag {
        let chain_id: ChainId = asset.token.chain_reference.into();
        let extra = asset
            .token
            .eip712
            .and_then(|eip712| serde_json::to_value(&eip712).ok());
        let requirements = v2::PaymentRequirements {
            scheme: ExactScheme.to_string(),
            pay_to: pay_to.into().to_string(),
            asset: asset.token.address.to_string(),
            network: chain_id,
            amount: asset.amount.to_string(),
            max_timeout_seconds: 300,
            extra,
        };
        v2::PriceTag {
            requirements,
            enricher: None,
        }
    }
}
