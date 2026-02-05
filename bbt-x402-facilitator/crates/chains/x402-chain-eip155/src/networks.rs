use x402_types::chain::ChainId;
use crate::chain::Eip155ChainReference;

/// Trait providing convenient methods to get instances for Etherlink (eip155 namespace).
///
/// This trait can be implemented for any type to provide static methods that create
/// instances for well-known EVM blockchain networks. Each method returns `Self`, allowing
/// the trait to be used with different types that need per-network configuration.
///
/// # Use Cases
///
/// - **ChainId**: Get CAIP-2 chain identifiers for EVM networks
/// - **Token Deployments**: Get per-chain token addresses (e.g., BBT on Etherlink)
/// - **Network Configuration**: Get network-specific configuration objects for EVM chains
/// - **Any Per-Network Data**: Any type that needs EVM network-specific instances
///
/// # Examples
///
/// ```ignore
/// use x402_rs::chain::ChainId;
/// use x402_rs::known::KnownNetworkEip155;
///
/// // Get Etherlink chain ID
/// let etherlink = ChainId::etherlink();
/// assert_eq!(etherlink.namespace, "eip155");
/// assert_eq!(etherlink.reference, "42793");
///
/// // Can also be implemented for other types like token addresses
/// // let bbt_etherlink = TokenAddress::etherlink();
/// ```
#[allow(dead_code)]
pub trait KnownNetworkEip155<A> {
    /// Returns the instance for Etherlink mainnet (eip155:42793)
    fn etherlink() -> A;
}

/// Implementation of KnownNetworkEip155 for ChainId.
///
/// Provides convenient static methods to create ChainId instances for well-known
/// EVM blockchain networks. Each method returns a properly configured ChainId with the
/// "eip155" namespace and the correct chain reference.
///
/// This is one example of implementing the KnownNetworkEip155 trait. Other types
/// (such as token address types) can also implement this trait to provide
/// per-network instances with better developer experience.
impl KnownNetworkEip155<ChainId> for ChainId {
    fn etherlink() -> ChainId {
        ChainId::new("eip155", "42793")
    }
}
impl KnownNetworkEip155<Eip155ChainReference> for Eip155ChainReference {
    fn etherlink() -> Eip155ChainReference {
        Eip155ChainReference::new(42793)
    }
}
