//! Type definitions for the V1 EIP-155 "exact" payment scheme.
//!
//! This module defines the wire format types for ERC-3009 based payments
//! on EVM chains using the V1 x402 protocol.

use alloy_primitives::{Address, B256, Bytes, U256};
use serde::{Deserialize, Serialize};
use x402_types::lit_str;
use x402_types::proto::v1;
use x402_types::timestamp::UnixTimestamp;

#[cfg(any(feature = "facilitator", feature = "client"))]
use alloy_sol_types::sol;

lit_str!(ExactScheme, "exact");

/// Type alias for V1 verify requests using the exact EVM payment scheme.
pub type VerifyRequest = v1::VerifyRequest<PaymentPayload, PaymentRequirements>;

/// Type alias for V1 settle requests (same structure as verify requests).
pub type SettleRequest = VerifyRequest;

/// Type alias for V1 payment payloads with EVM-specific data.
pub type PaymentPayload = v1::PaymentPayload<ExactScheme, ExactEvmPayload>;

/// Full payload required to authorize an ERC-3009 transfer.
///
/// This struct contains both the EIP-712 signature and the structured authorization
/// data that was signed. Together, they provide everything needed to execute a
/// `transferWithAuthorization` call on an ERC-3009 compliant token contract.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ExactEvmPayload {
    /// The cryptographic signature authorizing the transfer.
    ///
    /// This can be:
    /// - An EOA signature (64-65 bytes, split into r, s, v components)
    /// - An EIP-1271 signature (arbitrary length, validated by contract)
    /// - An EIP-6492 signature (wrapped with deployment data and magic suffix)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub signature: Option<Bytes>,

    /// The structured authorization data that was signed.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub authorization: Option<ExactEvmPayloadAuthorization>,

    /// Optional Permit2 payload (used instead of ERC-3009 authorization).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub permit2: Option<Permit2Payload>,

    /// Optional Permit2 payload (SignatureTransfer: PermitWitnessTransferFrom).
    ///
    /// This is the Coinbase x402-style Permit2 flow where:
    /// - The user signs an EIP-712 PermitWitnessTransferFrom message
    /// - The `spender` is an x402 Permit2 proxy contract (not the facilitator)
    /// - The proxy enforces `witness.to == payTo` on-chain
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub permit2_authorization: Option<Permit2Authorization>,
}

/// EIP-712 structured data for ERC-3009 transfer authorization.
///
/// This struct defines the parameters of a `transferWithAuthorization` call:
/// who can transfer tokens, to whom, how much, and during what time window.
/// The struct is signed using EIP-712 typed data signing.
#[derive(Debug, Copy, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ExactEvmPayloadAuthorization {
    /// The address authorizing the transfer (token owner).
    pub from: Address,

    /// The recipient address for the transfer.
    pub to: Address,

    /// The amount of tokens to transfer (in token's smallest unit).
    pub value: U256,

    /// The authorization is not valid before this timestamp (inclusive).
    pub valid_after: UnixTimestamp,

    /// The authorization expires at this timestamp (exclusive).
    pub valid_before: UnixTimestamp,

    /// A unique 32-byte nonce to prevent replay attacks.
    pub nonce: B256,
}

/// Permit2 authorization payload (AllowanceTransfer: PermitSingle).
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Permit2Payload {
    /// Owner authorizing the Permit2 allowance.
    pub owner: Address,

    /// The Permit2 PermitSingle data structure.
    pub permit_single: Permit2PermitSingle,

    /// The cryptographic signature authorizing the Permit2 allowance.
    pub signature: Bytes,
}

/// Permit2 PermitSingle data.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Permit2PermitSingle {
    pub details: Permit2Details,
    pub spender: Address,
    pub sig_deadline: u64,
}

/// Permit2 PermitDetails data.
#[derive(Debug, Copy, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Permit2Details {
    pub token: Address,
    pub amount: U256,
    pub expiration: u64,
    pub nonce: u64,
}

/// Permit2 authorization payload (SignatureTransfer: PermitWitnessTransferFrom).
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Permit2Authorization {
    /// Signer/owner authorizing the transfer.
    pub from: Address,

    /// Token and amount authorized for transfer.
    pub permitted: Permit2TokenPermissions,

    /// Must be the x402 Permit2 proxy address (not the facilitator).
    pub spender: Address,

    /// Permit2 signature nonce (uint256).
    pub nonce: U256,

    /// Permit2 signature deadline (unix seconds).
    pub deadline: UnixTimestamp,

    /// Witness data enforced by the x402 Permit2 proxy.
    pub witness: Permit2Witness,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Permit2TokenPermissions {
    pub token: Address,
    pub amount: U256,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Permit2Witness {
    pub to: Address,
    pub valid_after: UnixTimestamp,
    pub extra: Bytes,
}

/// Type alias for V1 payment requirements with EVM-specific types.
pub type PaymentRequirements =
    v1::PaymentRequirements<ExactScheme, U256, Address, PaymentRequirementsExtra>;

/// Extra EIP-712 domain parameters for token contracts.
///
/// Some token contracts require specific `name` and `version` values in their
/// EIP-712 domain for signature verification. This struct allows servers to
/// specify these values in the payment requirements, avoiding the need for
/// the facilitator to query them from the contract.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PaymentRequirementsExtra {
    /// The token name as used in the EIP-712 domain.
    pub name: String,

    /// The token version as used in the EIP-712 domain.
    pub version: String,
}

#[cfg(any(feature = "facilitator", feature = "client"))]
sol!(
    /// Solidity-compatible struct definition for ERC-3009 `transferWithAuthorization`.
    ///
    /// This matches the EIP-3009 format used in EIP-712 typed data:
    /// it defines the authorization to transfer tokens from `from` to `to`
    /// for a specific `value`, valid only between `validAfter` and `validBefore`
    /// and identified by a unique `nonce`.
    ///
    /// This struct is primarily used to reconstruct the typed data domain/message
    /// when verifying a client's signature.
    #[derive(Serialize, Deserialize)]
    struct TransferWithAuthorization {
        address from;
        address to;
        uint256 value;
        uint256 validAfter;
        uint256 validBefore;
        bytes32 nonce;
    }
);

#[cfg(any(feature = "facilitator", feature = "client"))]
sol!(
    /// Solidity-compatible struct for Permit2 `PermitDetails`.
    #[derive(Serialize, Deserialize)]
    struct PermitDetails {
        address token;
        uint160 amount;
        uint48 expiration;
        uint48 nonce;
    }
);

#[cfg(any(feature = "facilitator", feature = "client"))]
sol!(
    /// Solidity-compatible struct for Permit2 `PermitSingle`.
    #[derive(Serialize, Deserialize)]
    struct PermitSingle {
        PermitDetails details;
        address spender;
        uint256 sigDeadline;
    }
);

// Permit2 SignatureTransfer types (PermitWitnessTransferFrom).
#[cfg(any(feature = "facilitator", feature = "client"))]
sol!(
    /// Solidity-compatible struct for Permit2 `TokenPermissions` (SignatureTransfer).
    #[derive(Serialize, Deserialize)]
    struct TokenPermissions {
        address token;
        uint256 amount;
    }
);

#[cfg(any(feature = "facilitator", feature = "client"))]
sol!(
    /// Solidity-compatible struct for x402 witness data (SignatureTransfer).
    #[derive(Serialize, Deserialize)]
    struct Witness {
        address to;
        uint256 validAfter;
        bytes extra;
    }
);

#[cfg(any(feature = "facilitator", feature = "client"))]
sol!(
    /// Solidity-compatible struct for Permit2 `PermitWitnessTransferFrom` (SignatureTransfer).
    #[derive(Serialize, Deserialize)]
    struct PermitWitnessTransferFrom {
        TokenPermissions permitted;
        address spender;
        uint256 nonce;
        uint256 deadline;
        Witness witness;
    }
);
