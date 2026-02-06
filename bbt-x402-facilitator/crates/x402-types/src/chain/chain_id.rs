//! CAIP-2 chain identifier types for blockchain-agnostic identification.
//!
//! This module implements the [CAIP-2](https://standards.chainagnostic.org/CAIPs/caip-2) standard
//! for identifying blockchain networks in a chain-agnostic way. A CAIP-2 chain ID
//! consists of two parts separated by a colon:
//!
//! - **Namespace**: The blockchain ecosystem (e.g., `eip155` for EVM)
//! - **Reference**: The chain-specific identifier (e.g., `42793` for Etherlink)
//!
//! # Examples
//!
//! ```
//! use x402_types::chain::ChainId;
//!
//! // Create a chain ID for Etherlink mainnet
//! let etherlink = ChainId::new("eip155", "42793");
//! assert_eq!(etherlink.to_string(), "eip155:42793");
//!
//! // Parse from string
//! let etherlink: ChainId = "eip155:42793".parse().unwrap();
//! assert_eq!(etherlink.namespace, "eip155");
//! assert_eq!(etherlink.reference, "42793");
//! ```

use serde::{Deserialize, Deserializer, Serialize, Serializer, de};
use std::collections::HashSet;
use std::fmt;
use std::str::FromStr;

use crate::networks;

/// A CAIP-2 compliant blockchain identifier.
///
/// Chain IDs uniquely identify blockchain networks across different ecosystems.
/// The format is `namespace:reference` where:
///
/// - `namespace` identifies the blockchain family (e.g., `eip155`)
/// - `reference` identifies the specific chain within that family
///
/// # Serialization
///
/// Serializes to/from a colon-separated string: `"eip155:42793"`
///
/// # Example
///
/// ```
/// use x402_types::chain::ChainId;
///
/// let chain = ChainId::new("eip155", "42793");
/// let json = serde_json::to_string(&chain).unwrap();
/// assert_eq!(json, "\"eip155:42793\"");
/// ```
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct ChainId {
    /// The blockchain namespace (e.g., `eip155` for EVM chains).
    pub namespace: String,
    /// The chain-specific reference (e.g., `42793` for Etherlink).
    pub reference: String,
}

impl ChainId {
    /// Creates a new chain ID from namespace and reference components.
    ///
    /// # Example
    ///
    /// ```
    /// use x402_types::chain::ChainId;
    ///
    /// let etherlink = ChainId::new("eip155", "42793");
    /// assert_eq!(etherlink.namespace, "eip155");
    /// assert_eq!(etherlink.reference, "42793");
    /// ```
    pub fn new<N: Into<String>, R: Into<String>>(namespace: N, reference: R) -> Self {
        Self {
            namespace: namespace.into(),
            reference: reference.into(),
        }
    }

    /// Returns the namespace component of the chain ID.
    pub fn namespace(&self) -> &str {
        &self.namespace
    }

    /// Returns the reference component of the chain ID.
    pub fn reference(&self) -> &str {
        &self.reference
    }

    /// Creates a chain ID from a well-known network name.
    ///
    /// This method looks up the network name in the registry of known networks
    /// (see [`crate::networks`]) and returns the corresponding chain ID.
    ///
    /// # Example
    ///
    /// ```
    /// use x402_types::chain::ChainId;
    ///
    /// let etherlink = ChainId::from_network_name("etherlink").unwrap();
    /// assert_eq!(etherlink.to_string(), "eip155:42793");
    ///
    /// assert!(ChainId::from_network_name("unknown").is_none());
    /// ```
    pub fn from_network_name(network_name: &str) -> Option<Self> {
        networks::chain_id_by_network_name(network_name).cloned()
    }

    /// Returns the well-known network name for this chain ID, if any.
    ///
    /// This is the reverse of [`ChainId::from_network_name`].
    ///
    /// # Example
    ///
    /// ```
    /// use x402_types::chain::ChainId;
    ///
    /// let etherlink = ChainId::new("eip155", "42793");
    /// assert_eq!(etherlink.as_network_name(), Some("etherlink"));
    ///
    /// let unknown = ChainId::new("eip155", "999999");
    /// assert!(unknown.as_network_name().is_none());
    /// ```
    pub fn as_network_name(&self) -> Option<&'static str> {
        networks::network_name_by_chain_id(self)
    }
}

impl fmt::Display for ChainId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}:{}", self.namespace, self.reference)
    }
}

impl From<ChainId> for String {
    fn from(value: ChainId) -> Self {
        value.to_string()
    }
}

/// Error returned when parsing an invalid chain ID string.
///
/// A valid chain ID must be in the format `namespace:reference` where both
/// components are non-empty strings.
#[derive(Debug, thiserror::Error)]
#[error("Invalid chain id format {0}")]
pub struct ChainIdFormatError(String);

impl FromStr for ChainId {
    type Err = ChainIdFormatError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let parts: Vec<&str> = s.splitn(2, ':').collect();
        if parts.len() != 2 {
            return Err(ChainIdFormatError(s.into()));
        }
        Ok(ChainId {
            namespace: parts[0].into(),
            reference: parts[1].into(),
        })
    }
}

impl Serialize for ChainId {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_str(&self.to_string())
    }
}

impl<'de> Deserialize<'de> for ChainId {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let s = String::deserialize(deserializer)?;
        ChainId::from_str(&s).map_err(de::Error::custom)
    }
}

/// A pattern for matching chain IDs.
///
/// Chain ID patterns allow flexible matching of blockchain networks:
///
/// - **Wildcard**: Matches any chain within a namespace (e.g., `eip155:*` matches all EVM chains)
/// - **Exact**: Matches a specific chain (e.g., `eip155:42793` matches only Etherlink)
/// - **Set**: Matches any chain from a set (e.g., `eip155:{1,42793}` matches Ethereum or Etherlink)
///
/// # Serialization
///
/// Patterns serialize to human-readable strings:
/// - Wildcard: `"eip155:*"`
/// - Exact: `"eip155:42793"`
/// - Set: `"eip155:{1,42793}"`
///
/// # Example
///
/// ```
/// use x402_types::chain::{ChainId, ChainIdPattern};
///
/// // Match all EVM chains
/// let all_evm = ChainIdPattern::wildcard("eip155");
/// assert!(all_evm.matches(&ChainId::new("eip155", "42793")));
/// assert!(all_evm.matches(&ChainId::new("eip155", "1")));
///
/// // Match specific chain
/// let etherlink_only = ChainIdPattern::exact("eip155", "42793");
/// assert!(etherlink_only.matches(&ChainId::new("eip155", "42793")));
/// assert!(!etherlink_only.matches(&ChainId::new("eip155", "1")));
/// ```
#[derive(Debug, Clone)]
pub enum ChainIdPattern {
    /// Matches any chain within the specified namespace.
    Wildcard {
        /// The namespace to match (e.g., `eip155`).
        namespace: String,
    },
    /// Matches exactly one specific chain.
    Exact {
        /// The namespace of the chain.
        namespace: String,
        /// The reference of the chain.
        reference: String,
    },
    /// Matches any chain from a set of references within a namespace.
    Set {
        /// The namespace of the chains.
        namespace: String,
        /// The set of chain references to match.
        references: HashSet<String>,
    },
}

impl ChainIdPattern {
    /// Creates a wildcard pattern that matches any chain in the given namespace.
    ///
    /// # Example
    ///
    /// ```
    /// use x402_types::chain::{ChainId, ChainIdPattern};
    ///
    /// let pattern = ChainIdPattern::wildcard("eip155");
    /// assert!(pattern.matches(&ChainId::new("eip155", "1")));
    /// assert!(pattern.matches(&ChainId::new("eip155", "42793")));
    /// ```
    pub fn wildcard<S: Into<String>>(namespace: S) -> Self {
        Self::Wildcard {
            namespace: namespace.into(),
        }
    }

    /// Creates an exact pattern that matches only the specified chain.
    ///
    /// # Example
    ///
    /// ```
    /// use x402_types::chain::{ChainId, ChainIdPattern};
    ///
    /// let pattern = ChainIdPattern::exact("eip155", "42793");
    /// assert!(pattern.matches(&ChainId::new("eip155", "42793")));
    /// assert!(!pattern.matches(&ChainId::new("eip155", "1")));
    /// ```
    pub fn exact<N: Into<String>, R: Into<String>>(namespace: N, reference: R) -> Self {
        Self::Exact {
            namespace: namespace.into(),
            reference: reference.into(),
        }
    }

    /// Creates a set pattern that matches any chain from the given set of references.
    ///
    /// # Example
    ///
    /// ```
    /// use x402_types::chain::{ChainId, ChainIdPattern};
    /// use std::collections::HashSet;
    ///
    /// let refs: HashSet<String> = ["1", "42793"].iter().map(|s| s.to_string()).collect();
    /// let pattern = ChainIdPattern::set("eip155", refs);
    /// assert!(pattern.matches(&ChainId::new("eip155", "42793")));
    /// assert!(!pattern.matches(&ChainId::new("eip155", "42")));
    /// ```
    pub fn set<N: Into<String>>(namespace: N, references: HashSet<String>) -> Self {
        Self::Set {
            namespace: namespace.into(),
            references,
        }
    }

    /// Check if a `ChainId` matches this pattern.
    ///
    /// - `Wildcard` matches any chain with the same namespace
    /// - `Exact` matches only if both namespace and reference are equal
    /// - `Set` matches if the namespace is equal and the reference is in the set
    pub fn matches(&self, chain_id: &ChainId) -> bool {
        match self {
            ChainIdPattern::Wildcard { namespace } => chain_id.namespace == *namespace,
            ChainIdPattern::Exact {
                namespace,
                reference,
            } => chain_id.namespace == *namespace && chain_id.reference == *reference,
            ChainIdPattern::Set {
                namespace,
                references,
            } => chain_id.namespace == *namespace && references.contains(&chain_id.reference),
        }
    }

    /// Returns the namespace of this pattern.
    #[allow(dead_code)]
    pub fn namespace(&self) -> &str {
        match self {
            ChainIdPattern::Wildcard { namespace } => namespace,
            ChainIdPattern::Exact { namespace, .. } => namespace,
            ChainIdPattern::Set { namespace, .. } => namespace,
        }
    }
}

impl fmt::Display for ChainIdPattern {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ChainIdPattern::Wildcard { namespace } => write!(f, "{}:*", namespace),
            ChainIdPattern::Exact {
                namespace,
                reference,
            } => write!(f, "{}:{}", namespace, reference),
            ChainIdPattern::Set {
                namespace,
                references,
            } => {
                let refs: Vec<&str> = references.iter().map(|s| s.as_ref()).collect();
                write!(f, "{}:{{{}}}", namespace, refs.join(","))
            }
        }
    }
}

impl FromStr for ChainIdPattern {
    type Err = ChainIdFormatError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let (namespace, rest) = s.split_once(':').ok_or(ChainIdFormatError(s.into()))?;

        if namespace.is_empty() {
            return Err(ChainIdFormatError(s.into()));
        }

        // Wildcard: eip155:*
        if rest == "*" {
            return Ok(ChainIdPattern::wildcard(namespace));
        }

        // Set: eip155:{1,2,3}
        if let Some(inner) = rest.strip_prefix('{').and_then(|r| r.strip_suffix('}')) {
            let mut references = HashSet::new();

            for item in inner.split(',') {
                let item = item.trim();
                if item.is_empty() {
                    return Err(ChainIdFormatError(s.into()));
                }
                references.insert(item.into());
            }

            if references.is_empty() {
                return Err(ChainIdFormatError(s.into()));
            }

            return Ok(ChainIdPattern::set(namespace, references));
        }

        // Exact: eip155:1
        if rest.is_empty() {
            return Err(ChainIdFormatError(s.into()));
        }

        Ok(ChainIdPattern::exact(namespace, rest))
    }
}

impl Serialize for ChainIdPattern {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_str(&self.to_string())
    }
}

impl<'de> Deserialize<'de> for ChainIdPattern {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let s = String::deserialize(deserializer)?;
        ChainIdPattern::from_str(&s).map_err(de::Error::custom)
    }
}

impl From<ChainId> for ChainIdPattern {
    fn from(chain_id: ChainId) -> Self {
        ChainIdPattern::exact(chain_id.namespace, chain_id.reference)
    }
}

impl From<ChainIdPattern> for Vec<ChainIdPattern> {
    fn from(value: ChainIdPattern) -> Self {
        vec![value]
    }
}

impl From<ChainId> for Vec<ChainId> {
    fn from(value: ChainId) -> Self {
        vec![value]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::networks::{chain_id_by_network_name, network_name_by_chain_id};

    #[test]
    fn test_chain_id_serialize_eip155() {
        let chain_id = ChainId::new("eip155", "1");
        let serialized = serde_json::to_string(&chain_id).unwrap();
        assert_eq!(serialized, "\"eip155:1\"");
    }


    #[test]
    fn test_chain_id_deserialize_eip155() {
        let chain_id: ChainId = serde_json::from_str("\"eip155:1\"").unwrap();
        assert_eq!(chain_id.namespace, "eip155");
        assert_eq!(chain_id.reference, "1");
    }


    #[test]
    fn test_chain_id_roundtrip_eip155() {
        let original = ChainId::new("eip155", "42793");
        // let original = ChainId::eip155(42793);
        let serialized = serde_json::to_string(&original).unwrap();
        let deserialized: ChainId = serde_json::from_str(&serialized).unwrap();
        assert_eq!(original, deserialized);
    }


    #[test]
    fn test_chain_id_deserialize_invalid_format() {
        let result: Result<ChainId, _> = serde_json::from_str("\"invalid\"");
        assert!(result.is_err());
    }

    #[test]
    fn test_chain_id_deserialize_unknown_namespace() {
        let result: Result<ChainId, _> = serde_json::from_str("\"unknown:1\"");
        assert!(result.is_ok());
    }

    #[test]
    fn test_pattern_wildcard_matches() {
        let pattern = ChainIdPattern::wildcard("eip155");
        assert!(pattern.matches(&ChainId::new("eip155", "1")));
        assert!(pattern.matches(&ChainId::new("eip155", "42793")));
        assert!(pattern.matches(&ChainId::new("eip155", "137")));
    }

    #[test]
    fn test_pattern_exact_matches() {
        let pattern = ChainIdPattern::exact("eip155", "1");
        assert!(pattern.matches(&ChainId::new("eip155", "1")));
        assert!(!pattern.matches(&ChainId::new("eip155", "42793")));
    }

    #[test]
    fn test_pattern_set_matches() {
        let references: HashSet<String> = vec!["1", "42793", "137"]
            .into_iter()
            .map(String::from)
            .collect();
        let pattern = ChainIdPattern::set("eip155", references);
        assert!(pattern.matches(&ChainId::new("eip155", "1")));
        assert!(pattern.matches(&ChainId::new("eip155", "42793")));
        assert!(pattern.matches(&ChainId::new("eip155", "137")));
        assert!(!pattern.matches(&ChainId::new("eip155", "42")));
    }

    #[test]
    fn test_pattern_namespace() {
        let wildcard = ChainIdPattern::wildcard("eip155");
        assert_eq!(wildcard.namespace(), "eip155");

        let references: HashSet<String> = vec!["1"].into_iter().map(String::from).collect();
        let set = ChainIdPattern::set("eip155", references);
        assert_eq!(set.namespace(), "eip155");
    }

    #[test]
    fn test_chain_id_from_network_name() {
        let etherlink = chain_id_by_network_name("etherlink").unwrap();
        assert_eq!(etherlink.namespace, "eip155");
        assert_eq!(etherlink.reference, "42793");

        assert!(chain_id_by_network_name("unknown").is_none());
    }

    #[test]
    fn test_network_name_by_chain_id() {
        let chain_id = ChainId::new("eip155", "42793");
        let network_name = network_name_by_chain_id(&chain_id).unwrap();
        assert_eq!(network_name, "etherlink");

        let unknown_chain_id = ChainId::new("eip155", "999999");
        assert!(network_name_by_chain_id(&unknown_chain_id).is_none());
    }

    #[test]
    fn test_chain_id_as_network_name() {
        let chain_id = ChainId::new("eip155", "42793");
        assert_eq!(chain_id.as_network_name(), Some("etherlink"));

        let unknown_chain_id = ChainId::new("eip155", "999999");
        assert!(unknown_chain_id.as_network_name().is_none());
    }
}
