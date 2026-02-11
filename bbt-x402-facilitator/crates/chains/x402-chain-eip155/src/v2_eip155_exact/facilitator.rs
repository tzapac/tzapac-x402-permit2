//! Facilitator-side payment verification and settlement for V2 EIP-155 exact scheme.
//!
//! This module implements the facilitator logic for V2 protocol payments on EVM chains.
//! It reuses most of the V1 verification and settlement logic but handles V2-specific
//! payload structures with embedded requirements and CAIP-2 chain IDs.

use alloy_provider::Provider;
use std::str::FromStr;
use alloy_sol_types::Eip712Domain;
use std::collections::HashMap;
use x402_types::chain::{ChainId, ChainProviderOps};
use x402_types::proto;
use x402_types::proto::{PaymentVerificationError, v2};
use x402_types::timestamp::UnixTimestamp;
use x402_types::scheme::{
    X402SchemeFacilitator, X402SchemeFacilitatorBuilder, X402SchemeFacilitatorError,
};

#[cfg(feature = "telemetry")]
use tracing::instrument;

use crate::V2Eip155Exact;
use crate::chain::{Eip155ChainReference, Eip155MetaTransactionProvider};
use crate::v1_eip155_exact::ExactScheme;
use crate::v1_eip155_exact::facilitator::{
    Eip155ExactError, ExactEvmPayment, IEIP3009, IPermit2, Permit2Payment, Permit2WitnessPayment,
    X402ExactPermit2Proxy,
    assert_domain, assert_enough_balance, assert_enough_value, assert_permit2_domain,
    assert_permit2_time, assert_permit2_witness_domain, assert_permit2_witness_time, assert_time,
    settle_payment, settle_payment_permit2, settle_payment_permit2_witness,
    verify_payment, verify_payment_permit2, verify_payment_permit2_witness,
    x402_exact_permit2_proxy_address,
};
use crate::v2_eip155_exact::types;

impl<P> X402SchemeFacilitatorBuilder<P> for V2Eip155Exact
where
    P: Eip155MetaTransactionProvider + ChainProviderOps + Send + Sync + 'static,
    Eip155ExactError: From<P::Error>,
{
    fn build(
        &self,
        provider: P,
        _config: Option<serde_json::Value>,
    ) -> Result<Box<dyn X402SchemeFacilitator>, Box<dyn std::error::Error>> {
        Ok(Box::new(V2Eip155ExactFacilitator::new(provider)))
    }
}

/// Facilitator for V2 EIP-155 exact scheme payments.
///
/// This struct implements the [`X402SchemeFacilitator`] trait to provide payment
/// verification and settlement services for ERC-3009 based payments on EVM chains
/// using the V2 protocol.
///
/// # Type Parameters
///
/// - `P`: The provider type, which must implement [`Eip155MetaTransactionProvider`]
///   and [`ChainProviderOps`]
pub struct V2Eip155ExactFacilitator<P> {
    provider: P,
}

impl<P> V2Eip155ExactFacilitator<P> {
    /// Creates a new V2 EIP-155 exact scheme facilitator with the given provider.
    pub fn new(provider: P) -> Self {
        Self { provider }
    }
}

fn parse_signer_addresses(signers: Vec<String>) -> Result<Vec<alloy_primitives::Address>, Eip155ExactError> {
    let mut parsed = Vec::with_capacity(signers.len());
    for signer in signers {
        let addr = alloy_primitives::Address::from_str(&signer).map_err(|_| {
            PaymentVerificationError::InvalidFormat("Invalid signer address".to_string())
        })?;
        parsed.push(addr);
    }
    Ok(parsed)
}

#[async_trait::async_trait]
impl<P> X402SchemeFacilitator for V2Eip155ExactFacilitator<P>
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
        Ok(v2::VerifyResponse::valid(payer.to_string()).into())
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

        let (payer, tx_hash): (
            alloy_primitives::Address,
            alloy_primitives::TxHash,
        ) = match context {
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

        Ok(v2::SettleResponse::Success {
            payer: payer.to_string(),
            transaction: tx_hash.to_string(),
            network: payload.accepted.network.to_string(),
        }
        .into())
    }

    async fn supported(&self) -> Result<proto::SupportedResponse, X402SchemeFacilitatorError> {
        let chain_id = self.provider.chain_id();
        let kinds = vec![proto::SupportedPaymentKind {
            x402_version: v2::X402Version2.into(),
            scheme: ExactScheme.to_string(),
            network: chain_id.clone().into(),
            extra: None,
        }];
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

/// Runs all preconditions needed for a successful payment:
/// - Valid scheme, network, and receiver.
/// - Valid time window (validAfter/validBefore).
/// - Correct EIP-712 domain construction.
/// - Sufficient on-chain balance.
/// - Sufficient value in payload.
#[cfg_attr(feature = "telemetry", instrument(skip_all, err))]
async fn assert_valid_payment<'a, P: Provider>(
    provider: &'a P,
    chain: &'a Eip155ChainReference,
    payload: &'a types::PaymentPayload,
    requirements: &'a types::PaymentRequirements,
    allowed_spenders: Option<Vec<alloy_primitives::Address>>,
) -> Result<PaymentContext<'a, P>, Eip155ExactError> {
    let accepted = &payload.accepted;
    if accepted != requirements {
        return Err(PaymentVerificationError::AcceptedRequirementsMismatch.into());
    }
    let payload = &payload.payload;

    let chain_id: ChainId = chain.into();
    let payload_chain_id = &accepted.network;
    if payload_chain_id != &chain_id {
        return Err(PaymentVerificationError::ChainIdMismatch.into());
    }
    if let Some(asset_chain_id) = accepted.asset.chain_id() {
        if asset_chain_id != &chain_id {
            return Err(PaymentVerificationError::ChainIdMismatch.into());
        }
    }
    if let Some(asset_chain_id) = requirements.asset.chain_id() {
        if asset_chain_id != &chain_id {
            return Err(PaymentVerificationError::ChainIdMismatch.into());
        }
    }
    if let Some(permit2_auth) = payload.permit2_authorization.as_ref() {
        let proxy_address = x402_exact_permit2_proxy_address();
        let asset_address: alloy_primitives::Address = accepted.asset.address();
        let amount_required = accepted.amount;
        let amount_required_u256: alloy_primitives::U256 = amount_required.into();

        if permit2_auth.permitted.token != asset_address {
            return Err(PaymentVerificationError::AssetMismatch.into());
        }
        if permit2_auth.spender != proxy_address {
            return Err(PaymentVerificationError::InvalidFormat(
                "permit2Authorization.spender must be the x402 Permit2 proxy".to_string(),
            )
            .into());
        }
        if permit2_auth.witness.to != accepted.pay_to.address() {
            return Err(PaymentVerificationError::RecipientMismatch.into());
        }
        if permit2_auth.permitted.amount != amount_required_u256 {
            return Err(PaymentVerificationError::InvalidPaymentAmount.into());
        }

        assert_permit2_witness_time(
            permit2_auth.deadline,
            permit2_auth.witness.valid_after,
            accepted.max_timeout_seconds,
        )?;

        let erc20_contract = IEIP3009::new(asset_address, provider);
        assert_enough_balance(&erc20_contract, &permit2_auth.from, amount_required_u256).await?;

        let allowance = erc20_contract
            .allowance(permit2_auth.from, crate::v1_eip155_exact::facilitator::PERMIT2_ADDRESS)
            .call()
            .await
            .map_err(|e| PaymentVerificationError::TransactionSimulation(e.to_string()))?;
        if allowance < amount_required_u256 {
            return Err(PaymentVerificationError::TransactionSimulation(
                "Permit2 ERC20 allowance is insufficient".to_string(),
            )
            .into());
        }

        let signature = payload.signature.clone().ok_or_else(|| {
            PaymentVerificationError::InvalidFormat("Missing signature".to_string())
        })?;

        let domain = assert_permit2_witness_domain(chain);
        let contract = X402ExactPermit2Proxy::new(proxy_address, provider);
        let payment = Permit2WitnessPayment {
            from: permit2_auth.from,
            spender: permit2_auth.spender,
            token: asset_address,
            amount: permit2_auth.permitted.amount,
            nonce: permit2_auth.nonce,
            deadline: permit2_auth.deadline,
            pay_to: accepted.pay_to.address(),
            valid_after: permit2_auth.witness.valid_after,
            extra: permit2_auth.witness.extra.clone(),
            signature,
            transfer_amount: amount_required_u256,
        };

        Ok(PaymentContext::Permit2Witness {
            contract,
            payment,
            domain,
        })
    } else if let Some(permit2) = payload.permit2.as_ref() {
        let permit_single = &permit2.permit_single;
        let details = &permit_single.details;
        let asset_address: alloy_primitives::Address = accepted.asset.address();

        if details.token != asset_address {
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

        let amount_required = accepted.amount;
        assert_enough_value(&details.amount, &amount_required.into())?;

        let erc20_contract = IEIP3009::new(asset_address, provider);
        assert_enough_balance(&erc20_contract, &permit2.owner, amount_required.into()).await?;

        let domain = assert_permit2_domain(chain);
        let contract = IPermit2::new(
            crate::v1_eip155_exact::facilitator::PERMIT2_ADDRESS,
            provider,
        );
        let payment = Permit2Payment {
            owner: permit2.owner,
            spender: permit_single.spender,
            pay_to: accepted.pay_to.address(),
            token: details.token,
            amount: details.amount,
            expiration: details.expiration,
            nonce: details.nonce,
            sig_deadline: permit_single.sig_deadline,
            signature: permit2.signature.clone(),
            transfer_amount: amount_required.into(),
        };

        Ok(PaymentContext::Permit2 {
            contract,
            payment,
            domain,
        })
    } else {
        let authorization = payload.authorization.as_ref().ok_or_else(|| {
            PaymentVerificationError::InvalidFormat("Missing authorization".to_string())
        })?;
        if authorization.to != accepted.pay_to.address() {
            return Err(PaymentVerificationError::RecipientMismatch.into());
        }
        let valid_after = authorization.valid_after;
        let valid_before = authorization.valid_before;
        assert_time(valid_after, valid_before)?;
        let asset_address = accepted.asset.address();
        let contract = IEIP3009::new(asset_address, provider);

        let domain = assert_domain(chain, &contract, &asset_address, &accepted.extra).await?;

        let amount_required = accepted.amount;
        assert_enough_balance(&contract, &authorization.from, amount_required.into()).await?;
        assert_enough_value(&authorization.value, &amount_required.into())?;

        let payment = ExactEvmPayment {
            from: authorization.from,
            to: authorization.to,
            value: authorization.value,
            valid_after: authorization.valid_after,
            valid_before: authorization.valid_before,
            nonce: authorization.nonce,
            signature: payload.signature.clone().ok_or_else(|| {
                PaymentVerificationError::InvalidFormat("Missing signature".to_string())
            })?,
        };

        Ok(PaymentContext::Eip3009 {
            contract,
            payment,
            domain,
        })
    }
}
