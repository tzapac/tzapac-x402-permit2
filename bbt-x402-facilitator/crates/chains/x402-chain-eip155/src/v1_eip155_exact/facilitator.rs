//! Facilitator-side payment verification and settlement for V1 EIP-155 exact scheme.
//!
//! This module implements the facilitator logic for verifying and settling ERC-3009
//! payments on EVM chains. It handles:
//!
//! - Signature verification (EOA, EIP-1271, EIP-6492)
//! - Balance and amount validation
//! - EIP-712 domain construction
//! - On-chain settlement with gas management
//! - Smart wallet deployment for counterfactual signatures

use alloy_contract::SolCallBuilder;
use alloy_primitives::{Address, B256, Bytes, Signature, TxHash, U160, U256, address, hex};
use alloy_primitives::aliases::U48;
use alloy_provider::bindings::IMulticall3;
use alloy_provider::{
    MULTICALL3_ADDRESS, MulticallError, MulticallItem, PendingTransactionError, Provider,
};
use alloy_rpc_types_eth::TransactionRequest;
use alloy_network::TransactionBuilder;
use alloy_sol_types::{Eip712Domain, SolCall, SolStruct, SolType, eip712_domain, sol};
use alloy_transport::TransportError;
use std::collections::HashMap;
use std::str::FromStr;
use x402_types::chain::{ChainId, ChainProviderOps};
use x402_types::proto;
use x402_types::proto::{PaymentVerificationError, v1};
use x402_types::scheme::{
    X402SchemeFacilitator, X402SchemeFacilitatorBuilder, X402SchemeFacilitatorError,
};
use x402_types::timestamp::UnixTimestamp;

#[cfg(feature = "telemetry")]
use tracing::{Instrument, instrument};
#[cfg(feature = "telemetry")]
use tracing_core::Level;

use crate::V1Eip155Exact;
use crate::chain::{
    Eip155ChainReference, Eip155MetaTransactionProvider, MetaTransaction, MetaTransactionSendError,
};
use crate::v1_eip155_exact::{
    ExactScheme, PaymentRequirementsExtra, TransferWithAuthorization, types,
};

/// Signature verifier for EIP-6492, EIP-1271, EOA, universally deployed on the supported EVM chains
/// If absent on a target chain, verification will fail; you should deploy the validator there.
pub const VALIDATOR_ADDRESS: Address = address!("0xdAcD51A54883eb67D95FAEb2BBfdC4a9a6BD2a3B");

/// Permit2 contract address (canonical CREATE2 deployment).
pub const PERMIT2_ADDRESS: Address = address!("0x000000000022D473030F116dDEE9F6B43aC78BA3");

/// Default x402 Permit2 proxy address for the "exact" scheme.
///
/// Coinbase's x402 Permit2 flow uses a proxy as the `spender` in the signed message.
/// The proxy enforces `witness.to == payTo` on-chain (so the facilitator can't redirect funds).
///
/// Note: the proxy may not be deployed on all chains. For this Beta stack, the address can be
/// overridden via the `X402_EXACT_PERMIT2_PROXY_ADDRESS` environment variable.
pub const X402_EXACT_PERMIT2_PROXY_ADDRESS: Address =
    address!("0xB6FD384A0626BfeF85f3dBaf5223Dd964684B09E");

pub fn x402_exact_permit2_proxy_address() -> Address {
    if let Ok(raw) = std::env::var("X402_EXACT_PERMIT2_PROXY_ADDRESS") {
        Address::from_str(&raw).unwrap_or(X402_EXACT_PERMIT2_PROXY_ADDRESS)
    } else {
        X402_EXACT_PERMIT2_PROXY_ADDRESS
    }
}

impl<P> X402SchemeFacilitatorBuilder<P> for V1Eip155Exact
where
    P: Eip155MetaTransactionProvider + ChainProviderOps + Send + Sync + 'static,
    Eip155ExactError: From<P::Error>,
{
    fn build(
        &self,
        provider: P,
        _config: Option<serde_json::Value>,
    ) -> Result<Box<dyn X402SchemeFacilitator>, Box<dyn std::error::Error>> {
        Ok(Box::new(V1Eip155ExactFacilitator::new(provider)))
    }
}

/// Facilitator for V1 EIP-155 exact scheme payments.
///
/// This struct implements the [`X402SchemeFacilitator`] trait to provide payment
/// verification and settlement services for ERC-3009 based payments on EVM chains.
///
/// # Type Parameters
///
/// - `P`: The provider type, which must implement [`Eip155MetaTransactionProvider`]
///   and [`ChainProviderOps`]
pub struct V1Eip155ExactFacilitator<P> {
    provider: P,
}

impl<P> V1Eip155ExactFacilitator<P> {
    /// Creates a new V1 EIP-155 exact scheme facilitator with the given provider.
    pub fn new(provider: P) -> Self {
        Self { provider }
    }
}

fn parse_signer_addresses(signers: Vec<String>) -> Result<Vec<Address>, Eip155ExactError> {
    let mut parsed = Vec::with_capacity(signers.len());
    for signer in signers {
        let addr = Address::from_str(&signer).map_err(|_| {
            PaymentVerificationError::InvalidFormat("Invalid signer address".to_string())
        })?;
        parsed.push(addr);
    }
    Ok(parsed)
}

#[async_trait::async_trait]
impl<P> X402SchemeFacilitator for V1Eip155ExactFacilitator<P>
where
    P: Eip155MetaTransactionProvider + ChainProviderOps + Send + Sync,
    P::Inner: Provider,
    Eip155ExactError: From<P::Error>,
{
    async fn verify(
        &self,
        request: &proto::VerifyRequest,
    ) -> Result<proto::VerifyResponse, X402SchemeFacilitatorError> {
        let request = types::VerifyRequest::from_proto(request.clone())?;
        let payload = &request.payment_payload;
        let requirements = &request.payment_requirements;
        let allowed_spenders = parse_signer_addresses(self.provider.signer_addresses())?;
        let context = assert_valid_payment(
            self.provider.inner(),
            self.provider.chain(),
            payload,
            requirements,
            Some(allowed_spenders),
        )
        .await?;

        let payer = match context {
            PaymentContext::Eip3009 {
                contract,
                payment,
                domain,
            } => verify_payment(self.provider.inner(), &contract, &payment, &domain).await?,
            PaymentContext::Permit2 {
                contract,
                payment,
                domain,
            } => verify_payment_permit2(self.provider.inner(), &contract, &payment, &domain).await?,
            PaymentContext::Permit2Witness {
                contract,
                payment,
                domain,
            } => verify_payment_permit2_witness(self.provider.inner(), &contract, &payment, &domain).await?,
        };

        Ok(v1::VerifyResponse::valid(payer.to_string()).into())
    }

    async fn settle(
        &self,
        request: &proto::SettleRequest,
    ) -> Result<proto::SettleResponse, X402SchemeFacilitatorError> {
        let request = types::SettleRequest::from_proto(request.clone())?;
        let payload = &request.payment_payload;
        let requirements = &request.payment_requirements;
        let allowed_spenders = parse_signer_addresses(self.provider.signer_addresses())?;
        let context = assert_valid_payment(
            self.provider.inner(),
            self.provider.chain(),
            payload,
            requirements,
            Some(allowed_spenders),
        )
        .await?;

        let (payer, tx_hash) = match context {
            PaymentContext::Eip3009 {
                contract,
                payment,
                domain,
            } => (
                payment.from,
                settle_payment(&self.provider, &contract, &payment, &domain).await?,
            ),
            PaymentContext::Permit2 {
                contract,
                payment,
                domain,
            } => {
                let settlement =
                    settle_payment_permit2(&self.provider, &contract, &payment, &domain).await?;
                (
                    payment.owner,
                    settlement,
                )
            }
            PaymentContext::Permit2Witness {
                contract,
                payment,
                domain,
            } => (
                payment.from,
                settle_payment_permit2_witness(&self.provider, &contract, &payment, &domain).await?,
            ),
        };
        Ok(v1::SettleResponse::Success {
            payer: payer.to_string(),
            transaction: tx_hash.to_string(),
            network: payload.network.clone(),
        }
        .into())
    }

    async fn supported(&self) -> Result<proto::SupportedResponse, X402SchemeFacilitatorError> {
        let chain_id = self.provider.chain_id();
        let kinds = {
            let mut kinds = Vec::with_capacity(1);
            let network = chain_id.as_network_name();
            if let Some(network) = network {
                kinds.push(proto::SupportedPaymentKind {
                    x402_version: v1::X402Version1.into(),
                    scheme: ExactScheme.to_string(),
                    network: network.to_string(),
                    extra: None,
                });
            }
            kinds
        };
        let signers = {
            let mut signers = HashMap::with_capacity(1);
            signers.insert(chain_id, self.provider.signer_addresses());
            signers
        };
        Ok(proto::SupportedResponse {
            kinds,
            extensions: Vec::new(),
            signers,
        })
    }
}

/// A fully specified ERC-3009 authorization payload for EVM settlement.
#[derive(Debug)]
pub struct ExactEvmPayment {
    /// Authorized sender (`from`) — EOA or smart wallet.
    pub from: Address,
    /// Authorized recipient (`to`).
    pub to: Address,
    /// Transfer amount (token units).
    pub value: U256,
    /// Not valid before this timestamp (inclusive).
    pub valid_after: UnixTimestamp,
    /// Not valid at/after this timestamp (exclusive).
    pub valid_before: UnixTimestamp,
    /// Unique 32-byte nonce (prevents replay).
    pub nonce: B256,
    /// Raw signature bytes (EIP-1271 or EIP-6492-wrapped).
    pub signature: Bytes,
}

#[derive(Debug)]
pub struct Permit2Payment {
    /// Permit2 owner authorizing the allowance.
    pub owner: Address,
    /// Permit2 spender authorized to transfer.
    pub spender: Address,
    /// Recipient address for the transfer.
    pub pay_to: Address,
    /// Token address being authorized.
    pub token: Address,
    /// Permitted allowance amount (uint160 bounded).
    pub amount: U256,
    /// Permit2 allowance expiration timestamp.
    pub expiration: u64,
    /// Permit2 nonce (uint48 bounded).
    pub nonce: u64,
    /// Signature deadline timestamp.
    pub sig_deadline: u64,
    /// Raw Permit2 signature bytes.
    pub signature: Bytes,
    /// Amount to transfer for the settlement.
    pub transfer_amount: U256,
}

/// Coinbase-style Permit2 payment using SignatureTransfer (PermitWitnessTransferFrom).
#[derive(Debug)]
pub struct Permit2WitnessPayment {
    /// Signer/owner authorizing the transfer.
    pub from: Address,
    /// The x402 Permit2 proxy address (spender in the signed message).
    pub spender: Address,
    /// Token address being authorized.
    pub token: Address,
    /// Permitted amount (uint256).
    pub amount: U256,
    /// Permit2 nonce (uint256).
    pub nonce: U256,
    /// Signature deadline timestamp.
    pub deadline: UnixTimestamp,
    /// Witness destination (must equal payment requirements pay_to).
    pub pay_to: Address,
    /// Lower time bound (payment invalid before this time).
    pub valid_after: UnixTimestamp,
    /// Extra witness bytes.
    pub extra: Bytes,
    /// Raw signature bytes.
    pub signature: Bytes,
    /// Amount to transfer for the settlement (exact).
    pub transfer_amount: U256,
}

#[derive(Debug)]
enum PaymentContext<'a, P: Provider> {
    Eip3009 {
        contract: IEIP3009::IEIP3009Instance<&'a P>,
        payment: ExactEvmPayment,
        domain: Eip712Domain,
    },
    Permit2 {
        contract: IPermit2::IPermit2Instance<&'a P>,
        payment: Permit2Payment,
        domain: Eip712Domain,
    },
    Permit2Witness {
        contract: X402ExactPermit2Proxy::X402ExactPermit2ProxyInstance<&'a P>,
        payment: Permit2WitnessPayment,
        domain: Eip712Domain,
    },
}

sol!(
    #[allow(missing_docs)]
    #[allow(clippy::too_many_arguments)]
    #[derive(Debug)]
    #[sol(rpc)]
    IEIP3009,
    "abi/IEIP3009.json"
);

sol!(
    #[allow(missing_docs)]
    #[allow(clippy::too_many_arguments)]
    #[derive(Debug)]
    #[sol(rpc)]
    IPermit2,
    "abi/IPermit2.json"
);

sol! {
    #[allow(missing_docs)]
    #[allow(clippy::too_many_arguments)]
    #[derive(Debug)]
    #[sol(rpc)]
    X402ExactPermit2Proxy,
    "abi/X402ExactPermit2Proxy.json"
}

sol! {
    #[allow(missing_docs)]
    #[allow(clippy::too_many_arguments)]
    #[derive(Debug)]
    #[sol(rpc)]
    Validator6492,
    "abi/Validator6492.json"
}

/// Runs all preconditions needed for a successful payment:
/// - Valid scheme, network, and receiver.
/// - Valid time window (validAfter/validBefore).
/// - Correct EIP-712 domain construction.
/// - Sufficient on-chain balance.
/// - Sufficient value in payload.
#[cfg_attr(feature = "telemetry", instrument(skip_all, err))]
async fn assert_valid_payment<'a, P: Provider>(
    provider: &'a P,
    chain: &Eip155ChainReference,
    payload: &types::PaymentPayload,
    requirements: &types::PaymentRequirements,
    allowed_spenders: Option<Vec<Address>>,
) -> Result<PaymentContext<'a, P>, Eip155ExactError> {
    let chain_id: ChainId = chain.into();
    let payload_chain_id = ChainId::from_network_name(&payload.network)
        .ok_or(PaymentVerificationError::UnsupportedChain)?;
    if payload_chain_id != chain_id {
        return Err(PaymentVerificationError::ChainIdMismatch.into());
    }
    let requirements_chain_id = ChainId::from_network_name(&requirements.network)
        .ok_or(PaymentVerificationError::UnsupportedChain)?;
    if requirements_chain_id != chain_id {
        return Err(PaymentVerificationError::ChainIdMismatch.into());
    }
    if let Some(permit2_auth) = payload.payload.permit2_authorization.as_ref() {
        let proxy_address = x402_exact_permit2_proxy_address();

        // Static checks to align with Coinbase's Permit2 witness proxy flow.
        if permit2_auth.permitted.token != requirements.asset {
            return Err(PaymentVerificationError::AssetMismatch.into());
        }
        if permit2_auth.spender != proxy_address {
            return Err(PaymentVerificationError::InvalidFormat(
                "permit2Authorization.spender must be the x402 Permit2 proxy".to_string(),
            )
            .into());
        }
        if permit2_auth.witness.to != requirements.pay_to {
            return Err(PaymentVerificationError::RecipientMismatch.into());
        }

        let amount_required = requirements.max_amount_required;
        if permit2_auth.permitted.amount != amount_required {
            return Err(PaymentVerificationError::InvalidPaymentAmount.into());
        }

        assert_permit2_witness_time(permit2_auth.deadline, permit2_auth.witness.valid_after)?;

        let erc20_contract = IEIP3009::new(permit2_auth.permitted.token, provider);
        assert_enough_balance(&erc20_contract, &permit2_auth.from, amount_required).await?;

        // Permit2 SignatureTransfer still requires ERC20 approval for Permit2.
        let allowance = erc20_contract
            .allowance(permit2_auth.from, PERMIT2_ADDRESS)
            .call()
            .await
            .map_err(|e| PaymentVerificationError::TransactionSimulation(e.to_string()))?;
        if allowance < amount_required {
            return Err(PaymentVerificationError::TransactionSimulation(
                "Permit2 ERC20 allowance is insufficient".to_string(),
            )
            .into());
        }

        let signature = payload.payload.signature.clone().ok_or_else(|| {
            PaymentVerificationError::InvalidFormat("Missing signature".to_string())
        })?;

        let domain = assert_permit2_witness_domain(chain);
        let contract = X402ExactPermit2Proxy::new(proxy_address, provider);
        let payment = Permit2WitnessPayment {
            from: permit2_auth.from,
            spender: permit2_auth.spender,
            token: permit2_auth.permitted.token,
            amount: permit2_auth.permitted.amount,
            nonce: permit2_auth.nonce,
            deadline: permit2_auth.deadline,
            pay_to: permit2_auth.witness.to,
            valid_after: permit2_auth.witness.valid_after,
            extra: permit2_auth.witness.extra.clone(),
            signature,
            transfer_amount: amount_required,
        };
        Ok(PaymentContext::Permit2Witness {
            contract,
            payment,
            domain,
        })
    } else if let Some(permit2) = payload.payload.permit2.as_ref() {
        let permit_single = &permit2.permit_single;
        let details = &permit_single.details;

        if details.token != requirements.asset {
            return Err(PaymentVerificationError::AssetMismatch.into());
        }
        if let Some(spenders) = allowed_spenders.as_ref() {
            if !spenders.iter().any(|s| *s == permit_single.spender) {
                return Err(PaymentVerificationError::RecipientMismatch.into());
            }
        }

        let sig_deadline = UnixTimestamp::from_secs(permit_single.sig_deadline);
        let expiration = UnixTimestamp::from_secs(details.expiration);
        assert_permit2_time(sig_deadline, expiration)?;

        let amount_required = requirements.max_amount_required;
        assert_enough_value(&details.amount, &amount_required)?;

        let erc20_contract = IEIP3009::new(details.token, provider);
        assert_enough_balance(&erc20_contract, &permit2.owner, amount_required).await?;

        let domain = assert_permit2_domain(chain);
        let contract = IPermit2::new(PERMIT2_ADDRESS, provider);
        let payment = Permit2Payment {
            owner: permit2.owner,
            spender: permit_single.spender,
            pay_to: requirements.pay_to,
            token: details.token,
            amount: details.amount,
            expiration: details.expiration,
            nonce: details.nonce,
            sig_deadline: permit_single.sig_deadline,
            signature: permit2.signature.clone(),
            transfer_amount: amount_required,
        };
        Ok(PaymentContext::Permit2 {
            contract,
            payment,
            domain,
        })
    } else if let Some(authorization) = payload.payload.authorization.as_ref() {
        if authorization.to != requirements.pay_to {
            return Err(PaymentVerificationError::RecipientMismatch.into());
        }
        let valid_after = authorization.valid_after;
        let valid_before = authorization.valid_before;
        assert_time(valid_after, valid_before)?;
        let asset_address = requirements.asset;
        let contract = IEIP3009::new(asset_address, provider);

        let domain = assert_domain(chain, &contract, &asset_address, &requirements.extra).await?;

        let amount_required = requirements.max_amount_required;
        assert_enough_balance(&contract, &authorization.from, amount_required).await?;
        assert_enough_value(&authorization.value, &amount_required)?;

        let signature = payload.payload.signature.clone().ok_or_else(|| {
            PaymentVerificationError::InvalidFormat("Missing signature".to_string())
        })?;
        let payment = ExactEvmPayment {
            from: authorization.from,
            to: authorization.to,
            value: authorization.value,
            valid_after: authorization.valid_after,
            valid_before: authorization.valid_before,
            nonce: authorization.nonce,
            signature,
        };

        Ok(PaymentContext::Eip3009 {
            contract,
            payment,
            domain,
        })
    } else {
        Err(PaymentVerificationError::InvalidFormat(
            "Missing authorization or permit2 payload".to_string(),
        )
        .into())
    }
}

/// Validates that the current time is within the `validAfter` and `validBefore` bounds.
///
/// Adds a 6-second grace buffer when checking expiration to account for latency.
#[cfg_attr(feature = "telemetry", instrument(skip_all, err))]
pub fn assert_time(
    valid_after: UnixTimestamp,
    valid_before: UnixTimestamp,
) -> Result<(), PaymentVerificationError> {
    let now = UnixTimestamp::now();
    if valid_before < now + 6 {
        return Err(PaymentVerificationError::Expired);
    }
    if valid_after > now {
        return Err(PaymentVerificationError::Early);
    }
    Ok(())
}

#[cfg_attr(feature = "telemetry", instrument(skip_all, err))]
pub fn assert_permit2_time(
    sig_deadline: UnixTimestamp,
    expiration: UnixTimestamp,
) -> Result<(), PaymentVerificationError> {
    let now = UnixTimestamp::now();
    if sig_deadline < now + 6 {
        return Err(PaymentVerificationError::Expired);
    }
    if expiration < now + 6 {
        return Err(PaymentVerificationError::Expired);
    }
    Ok(())
}

#[cfg_attr(feature = "telemetry", instrument(skip_all, err))]
pub fn assert_permit2_witness_time(
    deadline: UnixTimestamp,
    valid_after: UnixTimestamp,
) -> Result<(), PaymentVerificationError> {
    let now = UnixTimestamp::now();
    if deadline < now + 6 {
        return Err(PaymentVerificationError::Expired);
    }
    if valid_after > now {
        return Err(PaymentVerificationError::Early);
    }
    Ok(())
}

pub fn assert_permit2_witness_domain(chain: &Eip155ChainReference) -> Eip712Domain {
    // Coinbase-style Permit2 typed data domain: name + chainId + verifyingContract (no version).
    eip712_domain! {
        name: "Permit2",
        chain_id: chain.inner(),
        verifying_contract: PERMIT2_ADDRESS,
    }
}

pub fn assert_permit2_domain(chain: &Eip155ChainReference) -> Eip712Domain {
    eip712_domain! {
        name: "Permit2",
        version: "1",
        chain_id: chain.inner(),
        verifying_contract: PERMIT2_ADDRESS,
    }
}

fn permit2_amount(amount: U256) -> Result<U160, PaymentVerificationError> {
    if amount > U256::from(U160::MAX) {
        return Err(PaymentVerificationError::InvalidFormat(
            "Permit2 amount exceeds uint160".to_string(),
        ));
    }
    let limbs = amount.as_limbs();
    Ok(U160::from_limbs([limbs[0], limbs[1], limbs[2]]))
}

const PERMIT2_U48_MAX: u64 = (1u64 << 48) - 1;

fn permit2_u48(value: u64, field: &str) -> Result<U48, PaymentVerificationError> {
    if value > PERMIT2_U48_MAX {
        return Err(PaymentVerificationError::InvalidFormat(format!(
            "Permit2 {field} exceeds uint48"
        )));
    }
    Ok(U48::from(value))
}

fn build_permit2_single_call(
    payment: &Permit2Payment,
) -> Result<IPermit2::PermitSingle, PaymentVerificationError> {
    let details = IPermit2::PermitDetails {
        token: payment.token,
        amount: permit2_amount(payment.amount)?,
        expiration: permit2_u48(payment.expiration, "expiration")?,
        nonce: permit2_u48(payment.nonce, "nonce")?,
    };
    Ok(IPermit2::PermitSingle {
        details,
        spender: payment.spender,
        sigDeadline: U256::from(payment.sig_deadline),
    })
}

fn build_permit2_proxy_permit(
    payment: &Permit2WitnessPayment,
) -> X402ExactPermit2Proxy::PermitTransferFrom {
    X402ExactPermit2Proxy::PermitTransferFrom {
        permitted: X402ExactPermit2Proxy::TokenPermissions {
            token: payment.token,
            amount: payment.amount,
        },
        nonce: payment.nonce,
        deadline: U256::from(payment.deadline.as_secs()),
    }
}

fn build_permit2_proxy_witness(payment: &Permit2WitnessPayment) -> X402ExactPermit2Proxy::Witness {
    X402ExactPermit2Proxy::Witness {
        to: payment.pay_to,
        validAfter: U256::from(payment.valid_after.as_secs()),
        extra: payment.extra.clone(),
    }
}

/// Constructs the correct EIP-712 domain for signature verification.
#[cfg_attr(feature = "telemetry", instrument(skip_all, err, fields(
    network = %chain.as_chain_id(),
    asset = %asset_address
)))]
pub async fn assert_domain<P: Provider>(
    chain: &Eip155ChainReference,
    token_contract: &IEIP3009::IEIP3009Instance<P>,
    asset_address: &Address,
    extra: &Option<PaymentRequirementsExtra>,
) -> Result<Eip712Domain, Eip155ExactError> {
    let name = extra.as_ref().map(|extra| extra.name.clone());
    let name = if let Some(name) = name {
        name
    } else {
        let name_b = token_contract.name();
        let name_fut = name_b.call().into_future();
        #[cfg(feature = "telemetry")]
        let name = name_fut
            .instrument(tracing::info_span!(
                "fetch_eip712_name",
                otel.kind = "client",
            ))
            .await?;
        #[cfg(not(feature = "telemetry"))]
        let name = name_fut.await?;
        name
    };
    let version = extra.as_ref().map(|extra| extra.version.clone());
    let version = if let Some(version) = version {
        version
    } else {
        let version_b = token_contract.version();
        let version_fut = version_b.call().into_future();
        #[cfg(feature = "telemetry")]
        let version = version_fut
            .instrument(tracing::info_span!(
                "fetch_eip712_version",
                otel.kind = "client",
            ))
            .await?;
        #[cfg(not(feature = "telemetry"))]
        let version = version_fut.await?;
        version
    };
    let domain = eip712_domain! {
        name: name,
        version: version,
        chain_id: chain.inner(),
        verifying_contract: *asset_address,
    };
    Ok(domain)
}

/// Checks if the payer has enough on-chain token balance to meet the `maxAmountRequired`.
///
/// Performs an `ERC20.balanceOf()` call using the token contract instance.
#[cfg_attr(feature = "telemetry", instrument(skip_all, err, fields(
    sender = %sender,
    max_required = %max_amount_required,
    token_contract = %ieip3009_token_contract.address()
)))]
pub async fn assert_enough_balance<P: Provider>(
    ieip3009_token_contract: &IEIP3009::IEIP3009Instance<P>,
    sender: &Address,
    max_amount_required: U256,
) -> Result<(), Eip155ExactError> {
    let balance_of = ieip3009_token_contract.balanceOf(*sender);
    let balance_fut = balance_of.call().into_future();
    #[cfg(feature = "telemetry")]
    let balance = balance_fut
        .instrument(tracing::info_span!(
            "fetch_token_balance",
            token_contract = %ieip3009_token_contract.address(),
            sender = %sender,
            otel.kind = "client"
        ))
        .await?;
    #[cfg(not(feature = "telemetry"))]
    let balance = balance_fut.await?;

    if balance < max_amount_required {
        Err(PaymentVerificationError::InsufficientFunds.into())
    } else {
        Ok(())
    }
}

/// Verifies that the declared `value` in the payload is sufficient for the required amount.
///
/// This is a static check (not on-chain) that compares two numbers.
#[cfg_attr(feature = "telemetry", instrument(skip_all, err, fields(
    sent = %sent,
    max_amount_required = %max_amount_required
)))]
pub fn assert_enough_value(
    sent: &U256,
    max_amount_required: &U256,
) -> Result<(), PaymentVerificationError> {
    if sent != max_amount_required {
        Err(PaymentVerificationError::InvalidPaymentAmount)
    } else {
        Ok(())
    }
}

/// Canonical data required to verify a signature.
#[derive(Debug, Clone)]
struct SignedMessage {
    /// Expected signer (an EOA or contract wallet).
    address: Address,
    /// 32-byte digest that was signed (typically an EIP-712 hash).
    hash: B256,
    /// Structured signature, either EIP-6492 or EIP-1271.
    signature: StructuredSignature,
}

impl SignedMessage {
    /// Construct a [`SignedMessage`] from an [`ExactEvmPayment`] and its
    /// corresponding [`Eip712Domain`].
    ///
    /// This helper ties together:
    /// - The **payment intent** (an ERC-3009 `TransferWithAuthorization` struct),
    /// - The **EIP-712 domain** used for signing,
    /// - And the raw signature bytes attached to the payment.
    ///
    /// Steps performed:
    /// 1. Build an in-memory [`TransferWithAuthorization`] struct from the
    ///    `ExactEvmPayment` fields (`from`, `to`, `value`, validity window, `nonce`).
    /// 2. Compute the **EIP-712 struct hash** for that transfer under the given
    ///    `domain`. This becomes the `hash` field of the signed message.
    /// 3. Parse the raw signature bytes into a [`StructuredSignature`], which
    ///    distinguishes between:
    ///    - EIP-1271 (plain signature), and
    ///    - EIP-6492 (counterfactual signature wrapper).
    /// 4. Assemble all parts into a [`SignedMessage`] and return it.
    pub fn extract(
        payment: &ExactEvmPayment,
        domain: &Eip712Domain,
    ) -> Result<Self, StructuredSignatureFormatError> {
        let transfer_with_authorization = TransferWithAuthorization {
            from: payment.from,
            to: payment.to,
            value: payment.value,
            validAfter: U256::from(payment.valid_after.as_secs()),
            validBefore: U256::from(payment.valid_before.as_secs()),
            nonce: payment.nonce,
        };
        let eip712_hash = transfer_with_authorization.eip712_signing_hash(domain);
        let structured_signature: StructuredSignature = StructuredSignature::try_from_bytes(
            payment.signature.clone(),
            payment.from,
            &eip712_hash,
        )?;
        let signed_message = Self {
            address: payment.from,
            hash: eip712_hash,
            signature: structured_signature,
        };
        Ok(signed_message)
    }

}

/// A structured representation of an Ethereum signature.
///
/// This enum normalizes two supported cases:
///
/// - **EIP-6492 wrapped signatures**: used for counterfactual contract wallets.
///   They include deployment metadata (factory + calldata) plus the inner
///   signature that the wallet contract will validate after deployment.
/// - **EIP-1271 signatures**: plain contract (or EOA-style) signatures.
#[derive(Debug, Clone)]
enum StructuredSignature {
    /// An EIP-6492 wrapped signature.
    EIP6492 {
        /// Factory contract that can deploy the wallet deterministically
        factory: Address,
        /// Calldata to invoke on the factory (often a CREATE2 deployment).
        factory_calldata: Bytes,
        /// Inner signature for the wallet itself, probably EIP-1271.
        inner: Bytes,
        /// Full original bytes including the 6492 wrapper and magic bytes suffix.
        original: Bytes,
    },
    /// Normalized EOA signature.
    #[allow(clippy::upper_case_acronyms)]
    EOA(Signature),
    /// A plain EIP-1271 or EOA signature (no 6492 wrappers).
    EIP1271(Bytes),
}

/// The fixed 32-byte magic suffix defined by [EIP-6492](https://eips.ethereum.org/EIPS/eip-6492).
///
/// Any signature ending with this constant is treated as a 6492-wrapped
/// signature; the preceding bytes are ABI-decoded as `(address factory, bytes factoryCalldata, bytes innerSig)`.
const EIP6492_MAGIC_SUFFIX: [u8; 32] =
    hex!("6492649264926492649264926492649264926492649264926492649264926492");

sol! {
    /// Solidity-compatible struct for decoding the prefix of an EIP-6492 signature.
    ///
    /// Matches the tuple `(address factory, bytes factoryCalldata, bytes innerSig)`.
    #[derive(Debug)]
    struct Sig6492 {
        address factory;
        bytes   factoryCalldata;
        bytes   innerSig;
    }
}

#[derive(Debug, thiserror::Error)]
pub enum StructuredSignatureFormatError {
    #[error(transparent)]
    InvalidEIP6492Format(alloy_sol_types::Error),
}

impl StructuredSignature {
    pub fn try_from_bytes(
        bytes: Bytes,
        expected_signer: Address,
        prehash: &B256,
    ) -> Result<Self, StructuredSignatureFormatError> {
        let is_eip6492 = bytes.len() >= 32 && bytes[bytes.len() - 32..] == EIP6492_MAGIC_SUFFIX;
        let signature = if is_eip6492 {
            let body = &bytes[..bytes.len() - 32];
            let sig6492 = Sig6492::abi_decode_params(body)
                .map_err(StructuredSignatureFormatError::InvalidEIP6492Format)?;
            StructuredSignature::EIP6492 {
                factory: sig6492.factory,
                factory_calldata: sig6492.factoryCalldata,
                inner: sig6492.innerSig,
                original: bytes,
            }
        } else {
            // Let's see if it is a EOA signature
            let eoa_signature = if bytes.len() == 65 {
                Signature::from_raw(&bytes).ok().map(|s| s.normalized_s())
            } else if bytes.len() == 64 {
                Some(Signature::from_erc2098(&bytes).normalized_s())
            } else {
                None
            };
            match eoa_signature {
                None => StructuredSignature::EIP1271(bytes),
                Some(s) => {
                    let is_expected_signer = s
                        .recover_address_from_prehash(prehash)
                        .ok()
                        .map(|r| r == expected_signer)
                        .unwrap_or(false);
                    if is_expected_signer {
                        StructuredSignature::EOA(s)
                    } else {
                        StructuredSignature::EIP1271(bytes)
                    }
                }
            }
        };
        Ok(signature)
    }
}

impl TryFrom<Bytes> for StructuredSignature {
    type Error = StructuredSignatureFormatError;

    /// Parse raw signature bytes into a `StructuredSignature`.
    ///
    /// Rules:
    /// - If the last 32 bytes equal [`EIP6492_MAGIC_SUFFIX`], the prefix is
    ///   decoded as a [`Sig6492`] struct and returned as
    ///   [`StructuredSignature::EIP6492`].
    /// - Otherwise, the bytes are returned as [`StructuredSignature::EIP1271`].
    fn try_from(bytes: Bytes) -> Result<Self, Self::Error> {
        let is_eip6492 = bytes.len() >= 32 && bytes[bytes.len() - 32..] == EIP6492_MAGIC_SUFFIX;
        let signature = if is_eip6492 {
            let body = &bytes[..bytes.len() - 32];
            let sig6492 = Sig6492::abi_decode_params(body)
                .map_err(StructuredSignatureFormatError::InvalidEIP6492Format)?;
            StructuredSignature::EIP6492 {
                factory: sig6492.factory,
                factory_calldata: sig6492.factoryCalldata,
                inner: sig6492.innerSig,
                original: bytes,
            }
        } else {
            StructuredSignature::EIP1271(bytes)
        };
        Ok(signature)
    }
}

pub struct TransferWithAuthorization0Call<P>(
    pub TransferWithAuthorizationCall<P, IEIP3009::transferWithAuthorization_0Call, Bytes>,
);

impl<'a, P: Provider> TransferWithAuthorization0Call<&'a P> {
    /// Constructs a full `transferWithAuthorization` call for a verified payment payload.
    ///
    /// This function prepares the transaction builder with gas pricing adapted to the network's
    /// capabilities (EIP-1559 or legacy) and packages it together with signature metadata
    /// into a [`TransferWithAuthorization0Call`] structure.
    ///
    /// This function does not perform any validation — it assumes inputs are already checked.
    pub fn new(
        contract: &'a IEIP3009::IEIP3009Instance<P>,
        payment: &ExactEvmPayment,
        signature: Bytes,
    ) -> Self {
        let from = payment.from;
        let to = payment.to;
        let value = payment.value;
        let valid_after = U256::from(payment.valid_after.as_secs());
        let valid_before = U256::from(payment.valid_before.as_secs());
        let nonce = payment.nonce;
        let tx = contract.transferWithAuthorization_0(
            from,
            to,
            value,
            valid_after,
            valid_before,
            nonce,
            signature.clone(),
        );
        TransferWithAuthorization0Call(TransferWithAuthorizationCall {
            tx,
            from,
            to,
            value,
            valid_after,
            valid_before,
            nonce,
            signature,
            contract_address: *contract.address(),
        })
    }
}

pub struct TransferWithAuthorization1Call<P>(
    pub TransferWithAuthorizationCall<P, IEIP3009::transferWithAuthorization_1Call, Signature>,
);

impl<'a, P: Provider> TransferWithAuthorization1Call<&'a P> {
    /// Constructs a full `transferWithAuthorization` call for a verified payment payload
    /// using split signature components (v, r, s).
    ///
    /// This function prepares the transaction builder with gas pricing adapted to the network's
    /// capabilities (EIP-1559 or legacy) and packages it together with signature metadata
    /// into a [`TransferWithAuthorization1Call`] structure.
    ///
    /// This function does not perform any validation — it assumes inputs are already checked.
    pub fn new(
        contract: &'a IEIP3009::IEIP3009Instance<P>,
        payment: &ExactEvmPayment,
        signature: Signature,
    ) -> Self {
        let from = payment.from;
        let to = payment.to;
        let value = payment.value;
        let valid_after = U256::from(payment.valid_after.as_secs());
        let valid_before = U256::from(payment.valid_before.as_secs());
        let nonce = payment.nonce;
        let v = 27 + (signature.v() as u8);
        let r = B256::from(signature.r());
        let s = B256::from(signature.s());
        let tx = contract.transferWithAuthorization_1(
            from,
            to,
            value,
            valid_after,
            valid_before,
            nonce,
            v,
            r,
            s,
        );
        TransferWithAuthorization1Call(TransferWithAuthorizationCall {
            tx,
            from,
            to,
            value,
            valid_after,
            valid_before,
            nonce,
            signature,
            contract_address: *contract.address(),
        })
    }
}

/// A prepared call to `transferWithAuthorization` (ERC-3009) including all derived fields.
///
/// This struct wraps the assembled call builder, making it reusable across verification
/// (`.call()`) and settlement (`.send()`) flows, along with context useful for tracing/logging.
pub struct TransferWithAuthorizationCall<P, TCall, TSignature> {
    /// The prepared call builder that can be `.call()`ed or `.send()`ed.
    pub tx: SolCallBuilder<P, TCall>,
    /// The sender (`from`) address for the authorization.
    pub from: Address,
    /// The recipient (`to`) address for the authorization.
    pub to: Address,
    /// The amount to transfer (value).
    pub value: U256,
    /// Start of the validity window (inclusive).
    pub valid_after: U256,
    /// End of the validity window (exclusive).
    pub valid_before: U256,
    /// 32-byte authorization nonce (prevents replay).
    pub nonce: B256,
    /// EIP-712 signature for the transfer authorization.
    pub signature: TSignature,
    /// Address of the token contract used for this transfer.
    pub contract_address: Address,
}

/// Check whether contract code is present at `address`.
///
/// Uses `eth_getCode` against this provider. This is useful after a counterfactual
/// deployment to confirm visibility on the sending RPC before submitting a
/// follow-up transaction.
async fn is_contract_deployed<P: Provider>(
    provider: &P,
    address: &Address,
) -> Result<bool, TransportError> {
    let bytes_fut = provider.get_code_at(*address).into_future();
    #[cfg(feature = "telemetry")]
    let bytes = bytes_fut
        .instrument(tracing::info_span!("get_code_at",
            address = %address,
            otel.kind = "client",
        ))
        .await?;
    #[cfg(not(feature = "telemetry"))]
    let bytes = bytes_fut.await?;
    Ok(!bytes.is_empty())
}

pub async fn verify_payment<P: Provider>(
    provider: &P,
    contract: &IEIP3009::IEIP3009Instance<&P>,
    payment: &ExactEvmPayment,
    eip712_domain: &Eip712Domain,
) -> Result<Address, Eip155ExactError> {
    let signed_message = SignedMessage::extract(payment, eip712_domain)?;

    let payer = signed_message.address;
    let hash = signed_message.hash;
    match signed_message.signature {
        StructuredSignature::EIP6492 {
            factory: _,
            factory_calldata: _,
            inner,
            original,
        } => {
            // Prepare the call to validate EIP-6492 signature
            let validator6492 = Validator6492::new(VALIDATOR_ADDRESS, &provider);
            let is_valid_signature_call =
                validator6492.isValidSigWithSideEffects(payer, hash, original);
            // Prepare the call to simulate transfer the funds
            let transfer_call = TransferWithAuthorization0Call::new(contract, payment, inner);
            let transfer_call = transfer_call.0;
            // Execute both calls in a single transaction simulation to accommodate for possible smart wallet creation
            let aggregate3 = provider
                .multicall()
                .add(is_valid_signature_call)
                .add(transfer_call.tx);
            let aggregate3_call = aggregate3.aggregate3();
            #[cfg(feature = "telemetry")]
            let (is_valid_signature_result, transfer_result) = aggregate3_call
                .instrument(tracing::info_span!("call_transferWithAuthorization_0",
                        from = %transfer_call.from,
                        to = %transfer_call.to,
                        value = %transfer_call.value,
                        valid_after = %transfer_call.valid_after,
                        valid_before = %transfer_call.valid_before,
                        nonce = %transfer_call.nonce,
                        signature = %transfer_call.signature,
                        token_contract = %transfer_call.contract_address,
                        otel.kind = "client",
                ))
                .await?;
            #[cfg(not(feature = "telemetry"))]
            let (is_valid_signature_result, transfer_result) = aggregate3_call.await?;
            let is_valid_signature_result = is_valid_signature_result
                .map_err(|e| PaymentVerificationError::InvalidSignature(e.to_string()))?;
            if !is_valid_signature_result {
                return Err(PaymentVerificationError::InvalidSignature(
                    "Chain reported signature to be invalid".to_string(),
                )
                .into());
            }
            transfer_result
                .map_err(|e| PaymentVerificationError::TransactionSimulation(e.to_string()))?;
        }
        StructuredSignature::EIP1271(signature) => {
            // It is EIP-1271 signature, which we can pass to the transfer simulation
            let transfer_call = TransferWithAuthorization0Call::new(contract, payment, signature);
            let transfer_call = transfer_call.0;
            let transfer_call_fut = transfer_call.tx.call().into_future();
            #[cfg(feature = "telemetry")]
            transfer_call_fut
                .instrument(tracing::info_span!("call_transferWithAuthorization_0",
                        from = %transfer_call.from,
                        to = %transfer_call.to,
                        value = %transfer_call.value,
                        valid_after = %transfer_call.valid_after,
                        valid_before = %transfer_call.valid_before,
                        nonce = %transfer_call.nonce,
                        signature = %transfer_call.signature,
                        token_contract = %transfer_call.contract_address,
                        otel.kind = "client",
                ))
                .await?;
            #[cfg(not(feature = "telemetry"))]
            transfer_call_fut.await?;
        }
        StructuredSignature::EOA(signature) => {
            // It is EOA signature, which we can pass to the transfer simulation of (r,s,v)-based transferWithAuthorization function
            let transfer_call = TransferWithAuthorization1Call::new(contract, payment, signature);
            let transfer_call = transfer_call.0;
            let transfer_call_fut = transfer_call.tx.call().into_future();
            #[cfg(feature = "telemetry")]
            transfer_call_fut
                .instrument(tracing::info_span!("call_transferWithAuthorization_1",
                        from = %transfer_call.from,
                        to = %transfer_call.to,
                        value = %transfer_call.value,
                        valid_after = %transfer_call.valid_after,
                        valid_before = %transfer_call.valid_before,
                        nonce = %transfer_call.nonce,
                        signature = %transfer_call.signature,
                        token_contract = %transfer_call.contract_address,
                        otel.kind = "client",
                ))
                .await?;
            #[cfg(not(feature = "telemetry"))]
            transfer_call_fut.await?;
        }
    }

    Ok(payer)
}

pub async fn verify_payment_permit2<P: Provider>(
    provider: &P,
    contract: &IPermit2::IPermit2Instance<&P>,
    payment: &Permit2Payment,
    eip712_domain: &Eip712Domain,
) -> Result<Address, Eip155ExactError> {
    let _ = eip712_domain;
    let payer = payment.owner;
    let signature_bytes = payment.signature.clone();
    let permit_single = build_permit2_single_call(payment)?;

    let permit_call = contract.permit(payment.owner, permit_single, signature_bytes);

    #[cfg(feature = "telemetry")]
    {
        let span = tracing::info_span!(
            "call_permit2_permit",
            owner = %payment.owner,
            spender = %payment.spender,
            token = %payment.token,
            amount = %payment.transfer_amount,
            otel.kind = "client",
        );
        let _guard = span.enter();
        permit_call
            .call()
            .await
            .map_err(|e| PaymentVerificationError::InvalidSignature(e.to_string()))?;
    }
    #[cfg(not(feature = "telemetry"))]
    permit_call
        .call()
        .await
        .map_err(|e| PaymentVerificationError::InvalidSignature(e.to_string()))?;

    let erc20_contract = IEIP3009::new(payment.token, provider);
    let allowance = erc20_contract
        .allowance(payment.owner, PERMIT2_ADDRESS)
        .call()
        .await
        .map_err(|e| PaymentVerificationError::TransactionSimulation(e.to_string()))?;
    if allowance < payment.transfer_amount {
        return Err(PaymentVerificationError::TransactionSimulation(
            "Permit2 ERC20 allowance is insufficient".to_string(),
        )
        .into());
    }

    let token_transfer =
        erc20_contract.transferFrom(payment.owner, payment.pay_to, payment.transfer_amount);
    let txr = TransactionRequest::default()
        .with_to(payment.token)
        .with_from(PERMIT2_ADDRESS)
        .with_input(token_transfer.calldata().clone());
    provider
        .call(txr)
        .await
        .map_err(|e| PaymentVerificationError::TransactionSimulation(e.to_string()))?;

    Ok(payer)
}

pub async fn verify_payment_permit2_witness<P: Provider>(
    provider: &P,
    contract: &X402ExactPermit2Proxy::X402ExactPermit2ProxyInstance<&P>,
    payment: &Permit2WitnessPayment,
    eip712_domain: &Eip712Domain,
) -> Result<Address, Eip155ExactError> {
    let payer = payment.from;

    // Build EIP-712 prehash for EIP-6492 classification/validation.
    let permit_witness_transfer_from = types::PermitWitnessTransferFrom {
        permitted: types::TokenPermissions {
            token: payment.token,
            amount: payment.amount,
        },
        spender: payment.spender,
        nonce: payment.nonce,
        deadline: U256::from(payment.deadline.as_secs()),
        witness: types::Witness {
            to: payment.pay_to,
            validAfter: U256::from(payment.valid_after.as_secs()),
            extra: payment.extra.clone(),
        },
    };
    let eip712_hash = permit_witness_transfer_from.eip712_signing_hash(eip712_domain);

    let structured_signature: StructuredSignature = StructuredSignature::try_from_bytes(
        payment.signature.clone(),
        payer,
        &eip712_hash,
    )?;

    let permit = build_permit2_proxy_permit(payment);
    let witness = build_permit2_proxy_witness(payment);

    match structured_signature {
        StructuredSignature::EIP6492 { inner, original, .. } => {
            // Validate wrapper (may deploy wallet), then simulate proxy settle with inner signature.
            let validator6492 = Validator6492::new(VALIDATOR_ADDRESS, &provider);
            let is_valid_signature_call =
                validator6492.isValidSigWithSideEffects(payer, eip712_hash, original);
            let settle_call = contract.settle(permit, payer, witness, inner);

            let aggregate3 = provider
                .multicall()
                .add(is_valid_signature_call)
                .add(settle_call);
            let aggregate3_call = aggregate3.aggregate3();

            #[cfg(feature = "telemetry")]
            let (is_valid_signature_result, settle_result) = aggregate3_call
                .instrument(tracing::info_span!(
                    "call_x402_exact_permit2_proxy_settle_6492",
                    owner = %payer,
                    token = %payment.token,
                    amount = %payment.transfer_amount,
                    to = %payment.pay_to,
                    otel.kind = "client",
                ))
                .await?;
            #[cfg(not(feature = "telemetry"))]
            let (is_valid_signature_result, settle_result) = aggregate3_call.await?;

            let is_valid_signature_result = is_valid_signature_result
                .map_err(|e| PaymentVerificationError::InvalidSignature(e.to_string()))?;
            if !is_valid_signature_result {
                return Err(PaymentVerificationError::InvalidSignature(
                    "Chain reported signature to be invalid".to_string(),
                )
                .into());
            }
            settle_result
                .map_err(|e| PaymentVerificationError::TransactionSimulation(e.to_string()))?;
        }
        _ => {
            // For EOA + EIP-1271, simulate proxy settle directly with provided signature bytes.
            let settle_call = contract.settle(permit, payer, witness, payment.signature.clone());
            let settle_fut = settle_call.call().into_future();
            #[cfg(feature = "telemetry")]
            settle_fut
                .instrument(tracing::info_span!(
                    "call_x402_exact_permit2_proxy_settle",
                    owner = %payer,
                    token = %payment.token,
                    amount = %payment.transfer_amount,
                    to = %payment.pay_to,
                    otel.kind = "client",
                ))
                .await
                .map_err(|e| PaymentVerificationError::TransactionSimulation(e.to_string()))?;
            #[cfg(not(feature = "telemetry"))]
            settle_fut
                .await
                .map_err(|e| PaymentVerificationError::TransactionSimulation(e.to_string()))?;
        }
    }

    Ok(payer)
}

pub async fn settle_payment<P, E>(
    provider: &P,
    contract: &IEIP3009::IEIP3009Instance<&P::Inner>,
    payment: &ExactEvmPayment,
    eip712_domain: &Eip712Domain,
) -> Result<TxHash, Eip155ExactError>
where
    P: Eip155MetaTransactionProvider<Error = E>,
    Eip155ExactError: From<E>,
{
    let signed_message = SignedMessage::extract(payment, eip712_domain)?;
    let payer = payment.from;
    let receipt = match signed_message.signature {
        StructuredSignature::EIP6492 {
            factory,
            factory_calldata,
            inner,
            original: _,
        } => {
            let is_contract_deployed = is_contract_deployed(provider.inner(), &payer).await?;
            let transfer_call = TransferWithAuthorization0Call::new(contract, payment, inner);
            let transfer_call = transfer_call.0;
            if is_contract_deployed {
                // transferWithAuthorization with inner signature
                let tx_fut = Eip155MetaTransactionProvider::send_transaction(
                    provider,
                    MetaTransaction {
                        to: transfer_call.tx.target(),
                        calldata: transfer_call.tx.calldata().clone(),
                        confirmations: 1,
                    },
                );
                #[cfg(feature = "telemetry")]
                let receipt = tx_fut
                    .instrument(tracing::info_span!("call_transferWithAuthorization_0",
                        from = %transfer_call.from,
                        to = %transfer_call.to,
                        value = %transfer_call.value,
                        valid_after = %transfer_call.valid_after,
                        valid_before = %transfer_call.valid_before,
                        nonce = %transfer_call.nonce,
                        signature = %transfer_call.signature,
                        token_contract = %transfer_call.contract_address,
                        sig_kind="EIP6492.deployed",
                        otel.kind = "client",
                    ))
                    .await?;
                #[cfg(not(feature = "telemetry"))]
                let receipt = tx_fut.await?;
                receipt
            } else {
                // deploy the smart wallet, and transferWithAuthorization with inner signature
                let deployment_call = IMulticall3::Call3 {
                    allowFailure: true,
                    target: factory,
                    callData: factory_calldata,
                };
                let transfer_with_authorization_call = IMulticall3::Call3 {
                    allowFailure: false,
                    target: transfer_call.tx.target(),
                    callData: transfer_call.tx.calldata().clone(),
                };
                let aggregate_call = IMulticall3::aggregate3Call {
                    calls: vec![deployment_call, transfer_with_authorization_call],
                };
                let tx_fut = Eip155MetaTransactionProvider::send_transaction(
                    provider,
                    MetaTransaction {
                        to: MULTICALL3_ADDRESS,
                        calldata: aggregate_call.abi_encode().into(),
                        confirmations: 1,
                    },
                );
                #[cfg(feature = "telemetry")]
                let receipt = tx_fut
                    .instrument(tracing::info_span!("call_transferWithAuthorization_0",
                        from = %transfer_call.from,
                        to = %transfer_call.to,
                        value = %transfer_call.value,
                        valid_after = %transfer_call.valid_after,
                        valid_before = %transfer_call.valid_before,
                        nonce = %transfer_call.nonce,
                        signature = %transfer_call.signature,
                        token_contract = %transfer_call.contract_address,
                        sig_kind="EIP6492.counterfactual",
                        otel.kind = "client",
                    ))
                    .await?;
                #[cfg(not(feature = "telemetry"))]
                let receipt = tx_fut.await?;
                receipt
            }
        }
        StructuredSignature::EIP1271(eip1271_signature) => {
            let transfer_call =
                TransferWithAuthorization0Call::new(contract, payment, eip1271_signature);
            let transfer_call = transfer_call.0;
            // transferWithAuthorization with eip1271 signature
            let tx_fut = Eip155MetaTransactionProvider::send_transaction(
                provider,
                MetaTransaction {
                    to: transfer_call.tx.target(),
                    calldata: transfer_call.tx.calldata().clone(),
                    confirmations: 1,
                },
            );
            #[cfg(feature = "telemetry")]
            let receipt = tx_fut
                .instrument(tracing::info_span!("call_transferWithAuthorization_0",
                    from = %transfer_call.from,
                    to = %transfer_call.to,
                    value = %transfer_call.value,
                    valid_after = %transfer_call.valid_after,
                    valid_before = %transfer_call.valid_before,
                    nonce = %transfer_call.nonce,
                    signature = %transfer_call.signature,
                    token_contract = %transfer_call.contract_address,
                    sig_kind="EIP1271",
                    otel.kind = "client",
                ))
                .await?;
            #[cfg(not(feature = "telemetry"))]
            let receipt = tx_fut.await?;
            receipt
        }
        StructuredSignature::EOA(signature) => {
            let transfer_call = TransferWithAuthorization1Call::new(contract, payment, signature);
            let transfer_call = transfer_call.0;
            // transferWithAuthorization with EOA signature
            let tx_fut = Eip155MetaTransactionProvider::send_transaction(
                provider,
                MetaTransaction {
                    to: transfer_call.tx.target(),
                    calldata: transfer_call.tx.calldata().clone(),
                    confirmations: 1,
                },
            );
            #[cfg(feature = "telemetry")]
            let receipt = tx_fut
                .instrument(tracing::info_span!("call_transferWithAuthorization_1",
                    from = %transfer_call.from,
                    to = %transfer_call.to,
                    value = %transfer_call.value,
                    valid_after = %transfer_call.valid_after,
                    valid_before = %transfer_call.valid_before,
                    nonce = %transfer_call.nonce,
                    signature = %transfer_call.signature,
                    token_contract = %transfer_call.contract_address,
                    sig_kind="EOA",
                    otel.kind = "client",
                ))
                .await?;
            #[cfg(not(feature = "telemetry"))]
            let receipt = tx_fut.await?;
            receipt
        }
    };
    let success = receipt.status();
    if success {
        #[cfg(feature = "telemetry")]
        tracing::event!(Level::INFO,
            status = "ok",
            tx = %receipt.transaction_hash,
            "transferWithAuthorization_0 succeeded"
        );
        Ok(receipt.transaction_hash)
    } else {
        #[cfg(feature = "telemetry")]
        tracing::event!(
            Level::WARN,
            status = "failed",
            tx = %receipt.transaction_hash,
            "transferWithAuthorization_0 failed"
        );
        Err(Eip155ExactError::TransactionReverted(
            receipt.transaction_hash,
        ))
    }
}

pub async fn settle_payment_permit2<P, E>(
    provider: &P,
    contract: &IPermit2::IPermit2Instance<&P::Inner>,
    payment: &Permit2Payment,
    eip712_domain: &Eip712Domain,
) -> Result<TxHash, Eip155ExactError>
where
    P: Eip155MetaTransactionProvider<Error = E>,
    Eip155ExactError: From<E>,
{
    let _ = eip712_domain;
    tracing::info!(
        "[DEBUG] settle_payment_permit2 START: owner={}, spender={}, pay_to={}, token={}, amount={}",
        payment.owner,
        payment.spender,
        payment.pay_to,
        payment.token,
        payment.amount
    );
    
    let signature_bytes = payment.signature.clone();
    let permit_single = build_permit2_single_call(payment)?;
    let transfer_amount = permit2_amount(payment.transfer_amount)?;

    tracing::info!("[DEBUG] calling permit() on Permit2 contract...");
    let permit_tx = contract.permit(payment.owner, permit_single, signature_bytes);
    let permit_tx_fut = Eip155MetaTransactionProvider::send_transaction_from(
        provider,
        MetaTransaction {
            to: permit_tx.target(),
            calldata: permit_tx.calldata().clone(),
            confirmations: 1,
        },
        payment.spender,
    );
    #[cfg(feature = "telemetry")]
    let permit_receipt = permit_tx_fut
        .instrument(tracing::info_span!(
            "call_permit2_permit",
            owner = %payment.owner,
            spender = %payment.spender,
            token = %payment.token,
            amount = %payment.amount,
            otel.kind = "client",
        ))
        .await?;
    #[cfg(not(feature = "telemetry"))]
    let permit_receipt = permit_tx_fut.await?;

    tracing::info!("[DEBUG] permit() completed, status={}", permit_receipt.status());
    if !permit_receipt.status() {
        tracing::error!("[DEBUG] permit() REVERTED!");
        return Err(Eip155ExactError::TransactionReverted(
            permit_receipt.transaction_hash,
        ));
    }

    tracing::info!("[DEBUG] calling transferFrom() on Permit2 contract...");
    let transfer_tx =
        contract.transferFrom(payment.owner, payment.pay_to, transfer_amount, payment.token);
    let transfer_tx_fut = Eip155MetaTransactionProvider::send_transaction_from(
        provider,
        MetaTransaction {
            to: transfer_tx.target(),
            calldata: transfer_tx.calldata().clone(),
            confirmations: 1,
        },
        payment.spender,
    );
    #[cfg(feature = "telemetry")]
    let transfer_receipt = transfer_tx_fut
        .instrument(tracing::info_span!(
            "call_permit2_transferFrom",
            owner = %payment.owner,
            to = %payment.pay_to,
            token = %payment.token,
            amount = %payment.transfer_amount,
            otel.kind = "client",
        ))
        .await?;
    #[cfg(not(feature = "telemetry"))]
    let transfer_receipt = transfer_tx_fut.await?;

    tracing::info!("[DEBUG] transferFrom() completed, status={}", transfer_receipt.status());
    if transfer_receipt.status() {
        tracing::info!("[DEBUG] settle_payment_permit2 SUCCESS, tx={}", transfer_receipt.transaction_hash);
        Ok(transfer_receipt.transaction_hash)
    } else {
        tracing::error!("[DEBUG] transferFrom() REVERTED!");
        Err(Eip155ExactError::TransactionReverted(
            transfer_receipt.transaction_hash,
        ))
    }
}

pub async fn settle_payment_permit2_witness<P, E>(
    provider: &P,
    contract: &X402ExactPermit2Proxy::X402ExactPermit2ProxyInstance<&P::Inner>,
    payment: &Permit2WitnessPayment,
    eip712_domain: &Eip712Domain,
) -> Result<TxHash, Eip155ExactError>
where
    P: Eip155MetaTransactionProvider<Error = E>,
    Eip155ExactError: From<E>,
{
    let _ = eip712_domain;

    let permit = build_permit2_proxy_permit(payment);
    let witness = build_permit2_proxy_witness(payment);
    let settle_tx = contract.settle(permit, payment.from, witness, payment.signature.clone());

    let tx_fut = Eip155MetaTransactionProvider::send_transaction(
        provider,
        MetaTransaction {
            to: settle_tx.target(),
            calldata: settle_tx.calldata().clone(),
            confirmations: 1,
        },
    );

    #[cfg(feature = "telemetry")]
    let receipt = tx_fut
        .instrument(tracing::info_span!(
            "send_x402_exact_permit2_proxy_settle",
            owner = %payment.from,
            token = %payment.token,
            amount = %payment.transfer_amount,
            to = %payment.pay_to,
            otel.kind = "client",
        ))
        .await?;
    #[cfg(not(feature = "telemetry"))]
    let receipt = tx_fut.await?;

    if receipt.status() {
        Ok(receipt.transaction_hash)
    } else {
        Err(Eip155ExactError::TransactionReverted(receipt.transaction_hash))
    }
}

#[derive(Debug, thiserror::Error)]
pub enum Eip155ExactError {
    #[error(transparent)]
    Transport(#[from] TransportError),
    #[error(transparent)]
    PendingTransaction(#[from] PendingTransactionError),
    #[error("Transaction {0} reverted")]
    TransactionReverted(TxHash),
    #[error("Contract call failed: {0}")]
    ContractCall(String),
    #[error(transparent)]
    PaymentVerification(#[from] PaymentVerificationError),
}

impl From<Eip155ExactError> for X402SchemeFacilitatorError {
    fn from(value: Eip155ExactError) -> Self {
        match value {
            Eip155ExactError::Transport(_) => Self::OnchainFailure(value.to_string()),
            Eip155ExactError::PendingTransaction(_) => Self::OnchainFailure(value.to_string()),
            Eip155ExactError::TransactionReverted(_) => Self::OnchainFailure(value.to_string()),
            Eip155ExactError::ContractCall(_) => Self::OnchainFailure(value.to_string()),
            Eip155ExactError::PaymentVerification(e) => Self::PaymentVerification(e),
        }
    }
}

impl From<StructuredSignatureFormatError> for Eip155ExactError {
    fn from(e: StructuredSignatureFormatError) -> Self {
        Self::PaymentVerification(PaymentVerificationError::InvalidSignature(e.to_string()))
    }
}

impl From<MetaTransactionSendError> for Eip155ExactError {
    fn from(e: MetaTransactionSendError) -> Self {
        match e {
            MetaTransactionSendError::Transport(e) => Self::Transport(e),
            MetaTransactionSendError::PendingTransaction(e) => Self::PendingTransaction(e),
            MetaTransactionSendError::Custom(e) => Self::ContractCall(e),
        }
    }
}

impl From<MulticallError> for Eip155ExactError {
    fn from(e: MulticallError) -> Self {
        match e {
            MulticallError::ValueTx => Self::PaymentVerification(
                PaymentVerificationError::TransactionSimulation(e.to_string()),
            ),
            MulticallError::DecodeError(_) => Self::PaymentVerification(
                PaymentVerificationError::TransactionSimulation(e.to_string()),
            ),
            MulticallError::NoReturnData => Self::PaymentVerification(
                PaymentVerificationError::TransactionSimulation(e.to_string()),
            ),
            MulticallError::CallFailed(_) => Self::PaymentVerification(
                PaymentVerificationError::TransactionSimulation(e.to_string()),
            ),
            MulticallError::TransportError(transport_error) => Self::Transport(transport_error),
        }
    }
}

impl From<alloy_contract::Error> for Eip155ExactError {
    fn from(e: alloy_contract::Error) -> Self {
        match e {
            alloy_contract::Error::UnknownFunction(_) => Self::ContractCall(e.to_string()),
            alloy_contract::Error::UnknownSelector(_) => Self::ContractCall(e.to_string()),
            alloy_contract::Error::NotADeploymentTransaction => Self::ContractCall(e.to_string()),
            alloy_contract::Error::ContractNotDeployed => Self::ContractCall(e.to_string()),
            alloy_contract::Error::ZeroData(_, _) => Self::ContractCall(e.to_string()),
            alloy_contract::Error::AbiError(_) => Self::ContractCall(e.to_string()),
            alloy_contract::Error::TransportError(e) => Self::Transport(e),
            alloy_contract::Error::PendingTransactionError(e) => Self::PendingTransaction(e),
        }
    }
}
