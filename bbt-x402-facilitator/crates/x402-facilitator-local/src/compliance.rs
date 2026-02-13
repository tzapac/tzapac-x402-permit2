//! Compliance controls for facilitator-side request filtering.

use std::env;
use std::fs::{create_dir_all, OpenOptions};
use std::io::Write;
use std::path::Path;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use reqwest::StatusCode;
use serde::Serialize;
use serde_json::json;
use serde_json::Value;
use x402_types::proto::PaymentVerificationError;

#[derive(Clone, Debug)]
pub struct ComplianceGate {
    enabled: bool,
    deny_list: Vec<String>,
    allow_list: Vec<String>,
    provider: ComplianceProvider,
    audit_log_path: Option<String>,
}

#[derive(Clone, Debug)]
enum ComplianceProvider {
    Lists,
    Chainalysis(ChainalysisConfig),
}

#[derive(Clone, Debug)]
struct ChainalysisConfig {
    rest_url: String,
    api_key: String,
    blocked_status: String,
    timeout_ms: u64,
    fail_closed: bool,
}

enum ChainalysisResult {
    Allowed,
    Denied(String),
    Unknown(String),
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct CompliancePartyRecord {
    role: String,
    address: String,
    status: String,
    provider: String,
    reason: Option<String>,
}

#[derive(Debug)]
struct CompliancePartyCheckFailure {
    party: CompliancePartyRecord,
    error: PaymentVerificationError,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ComplianceAuditEvent {
    event_type: String,
    request_type: String,
    timestamp_ms: u128,
    outcome: String,
    provider: String,
    payer: Option<String>,
    payee: Option<String>,
    wallet: Option<String>,
    user_agent: Option<String>,
    reason: Option<String>,
    parties: Vec<CompliancePartyRecord>,
    metadata: Option<Value>,
}

impl ComplianceGate {
    pub fn enabled(&self) -> bool {
        self.enabled
    }

    pub fn disabled() -> Self {
        Self {
            enabled: false,
            deny_list: Vec::new(),
            allow_list: Vec::new(),
            provider: ComplianceProvider::Lists,
            audit_log_path: None,
        }
    }

    pub fn from_env() -> Result<Self, String> {
        let raw_enabled = env::var("COMPLIANCE_SCREENING_ENABLED").unwrap_or_else(|_| "true".to_string());
        let enabled = parse_bool(raw_enabled.as_str());

        let deny_list = parse_address_list("COMPLIANCE_DENY_LIST")?;
        let allow_list = parse_address_list("COMPLIANCE_ALLOW_LIST")?;

        if enabled && deny_list.iter().any(|addr| !is_valid_address(addr)) {
            return Err("COMPLIANCE_DENY_LIST contains an invalid address format".to_string());
        }
        if enabled && allow_list.iter().any(|addr| !is_valid_address(addr)) {
            return Err("COMPLIANCE_ALLOW_LIST contains an invalid address format".to_string());
        }

        let provider = match env::var("COMPLIANCE_PROVIDER")
            .unwrap_or_else(|_| "chainalysis".to_string())
            .to_lowercase()
            .as_str()
        {
            "chainalysis" => ComplianceProvider::Chainalysis(ChainalysisConfig::from_env()?),
            _ => ComplianceProvider::Lists,
        };

        let audit_log_path = env::var("COMPLIANCE_AUDIT_LOG")
            .ok()
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty());

        Ok(Self {
            enabled,
            deny_list,
            allow_list,
            provider,
            audit_log_path,
        })
    }

    pub async fn validate_for_request(
        &self,
        request_type: &str,
        payer: Option<&str>,
        payee: Option<&str>,
    ) -> Result<(), PaymentVerificationError> {
        if !self.enabled {
            self.record_audit(ComplianceAuditEvent {
                event_type: "compliance_check".to_string(),
                request_type: request_type.to_string(),
                timestamp_ms: current_timestamp_ms(),
                outcome: "disabled".to_string(),
                provider: self.provider_name().to_string(),
                payer: payer.map(str::to_lowercase),
                payee: payee.map(str::to_lowercase),
                wallet: None,
                user_agent: None,
                reason: Some("compliance disabled".to_string()),
                parties: Vec::new(),
                metadata: None,
            });
            return Ok(());
        }

        let mut party_records = Vec::new();

        if let Some(payer_raw) = payer {
            let payer_normalized = normalize_address(payer_raw)
                .ok_or_else(|| PaymentVerificationError::ComplianceFailed("payer has an invalid address format".to_string()))?;

            match self.validate_party("payer", &payer_normalized).await {
                Ok(record) => party_records.push(record),
                Err(failure) => {
                    self.record_audit(ComplianceAuditEvent {
                        event_type: "compliance_check".to_string(),
                        request_type: request_type.to_string(),
                        timestamp_ms: current_timestamp_ms(),
                        outcome: "denied".to_string(),
                        provider: self.provider_name().to_string(),
                        payer: Some(payer_normalized),
                        payee: payee.map(str::to_lowercase),
                        wallet: None,
                        user_agent: None,
                        reason: Some(format!("{}", failure.error)),
                        parties: vec![failure.party],
                        metadata: None,
                    });
                    return Err(failure.error);
                }
            }
        }

        if let Some(payee_raw) = payee {
            let payee_normalized = normalize_address(payee_raw)
                .ok_or_else(|| PaymentVerificationError::ComplianceFailed("payee has an invalid address format".to_string()))?;

            match self.validate_party("payee", &payee_normalized).await {
                Ok(record) => party_records.push(record),
                Err(failure) => {
                    self.record_audit(ComplianceAuditEvent {
                        event_type: "compliance_check".to_string(),
                        request_type: request_type.to_string(),
                        timestamp_ms: current_timestamp_ms(),
                        outcome: "denied".to_string(),
                        provider: self.provider_name().to_string(),
                        payer: payer.map(str::to_lowercase),
                        payee: Some(payee_normalized),
                        wallet: None,
                        user_agent: None,
                        reason: Some(format!("{}", failure.error)),
                        parties: party_records
                            .into_iter()
                            .chain(std::iter::once(failure.party))
                            .collect(),
                        metadata: None,
                    });
                    return Err(failure.error);
                }
            }
        }

        self.record_audit(ComplianceAuditEvent {
            event_type: "compliance_check".to_string(),
            request_type: request_type.to_string(),
            timestamp_ms: current_timestamp_ms(),
            outcome: "allowed".to_string(),
            provider: self.provider_name().to_string(),
            payer: payer.map(str::to_lowercase),
            payee: payee.map(str::to_lowercase),
            wallet: None,
            user_agent: None,
            reason: None,
            parties: party_records,
            metadata: None,
        });

        Ok(())
    }

    pub async fn validate(
        &self,
        payer: Option<&str>,
        payee: Option<&str>,
    ) -> Result<(), PaymentVerificationError> {
        self.validate_for_request("request", payer, payee).await
    }

    pub fn log_connection(
        &self,
        wallet: &str,
        reason: Option<&str>,
        source: Option<&str>,
        user_agent: Option<&str>,
        metadata: Option<Value>,
    ) {
        let address = normalize_address(wallet);
        let outcome = if address.is_some() { "accepted" } else { "invalid_address" };
        let mut event_metadata = metadata.unwrap_or_else(|| json!({}));
        if !event_metadata.is_object() {
            event_metadata = json!({
                "metadataType": event_metadata.to_string(),
            });
        }

        if let Some(obj) = event_metadata.as_object_mut() {
            obj.insert("source".to_string(), json!(source.unwrap_or("wallet_client")));
            obj.insert("provider".to_string(), json!(self.provider_name()));
            if let Some(address) = address.as_ref() {
                obj.insert("normalizedAddress".to_string(), json!(address));
            }
        }

        self.record_audit(ComplianceAuditEvent {
            event_type: "connection".to_string(),
            request_type: "connect".to_string(),
            timestamp_ms: current_timestamp_ms(),
            outcome: outcome.to_string(),
            provider: self.provider_name().to_string(),
            payer: address,
            payee: None,
            wallet: Some(wallet.to_string()),
            user_agent: user_agent.map(ToString::to_string),
            reason: reason.map(ToString::to_string),
            parties: Vec::new(),
            metadata: Some(event_metadata),
        });
    }

    async fn validate_party(&self, role: &str, address: &str) -> Result<CompliancePartyRecord, CompliancePartyCheckFailure> {
        if self
            .deny_list
            .iter()
            .any(|denied| denied.as_str() == address)
        {
            let party = CompliancePartyRecord {
                role: role.to_string(),
                address: address.to_string(),
                status: "denied".to_string(),
                provider: self.provider_name().to_string(),
                reason: Some("address is explicitly denied".to_string()),
            };
            return Err(CompliancePartyCheckFailure {
                party,
                error: PaymentVerificationError::ComplianceFailed(format!(
                    "{role} is denied by compliance policy: {address}"
                )),
            });
        }

        if !self.allow_list.is_empty() && !self.allow_list.iter().any(|allowed| allowed == address) {
            let party = CompliancePartyRecord {
                role: role.to_string(),
                address: address.to_string(),
                status: "denied".to_string(),
                provider: self.provider_name().to_string(),
                reason: Some("address is not in compliance allow-list".to_string()),
            };
            return Err(CompliancePartyCheckFailure {
                party,
                error: PaymentVerificationError::ComplianceFailed(format!(
                    "{role} is not in compliance allow-list: {address}"
                )),
            });
        }

        match &self.provider {
            ComplianceProvider::Lists => Ok(CompliancePartyRecord {
                role: role.to_string(),
                address: address.to_string(),
                status: "passed".to_string(),
                provider: self.provider_name().to_string(),
                reason: None,
            }),
            ComplianceProvider::Chainalysis(config) => {
                let status = query_chainalysis(address, config).await.map_err(|error| {
                    CompliancePartyCheckFailure {
                        party: CompliancePartyRecord {
                            role: role.to_string(),
                            address: address.to_string(),
                            status: "unknown".to_string(),
                            provider: self.provider_name().to_string(),
                            reason: Some(format!("chainalysis query failed: {error}")),
                        },
                        error,
                    }
                })?;
                match status {
                    ChainalysisResult::Allowed => Ok(CompliancePartyRecord {
                        role: role.to_string(),
                        address: address.to_string(),
                        status: "passed".to_string(),
                        provider: self.provider_name().to_string(),
                        reason: Some("chainalysis clear".to_string()),
                    }),
                    ChainalysisResult::Denied(reason) => {
                        let party = CompliancePartyRecord {
                            role: role.to_string(),
                            address: address.to_string(),
                            status: "denied".to_string(),
                            provider: self.provider_name().to_string(),
                            reason: Some(reason.clone()),
                        };
                        Err(CompliancePartyCheckFailure {
                            party,
                            error: PaymentVerificationError::ComplianceFailed(format!(
                                "{role} failed provider screening: {reason}"
                            )),
                        })
                    }
                    ChainalysisResult::Unknown(reason) => {
                        if config.fail_closed {
                            let party = CompliancePartyRecord {
                                role: role.to_string(),
                                address: address.to_string(),
                                status: "denied".to_string(),
                                provider: self.provider_name().to_string(),
                                reason: Some(reason.clone()),
                            };
                            Err(CompliancePartyCheckFailure {
                                party,
                                error: PaymentVerificationError::ComplianceFailed(format!(
                                    "{role} screening result unresolved: {reason}"
                                )),
                            })
                        } else {
                            Ok(CompliancePartyRecord {
                                role: role.to_string(),
                                address: address.to_string(),
                                status: "warn".to_string(),
                                provider: self.provider_name().to_string(),
                                reason: Some(reason),
                            })
                        }
                    }
                }
            }
        }
    }

    fn provider_name(&self) -> &'static str {
        match self.provider {
            ComplianceProvider::Lists => "lists",
            ComplianceProvider::Chainalysis(_) => "chainalysis",
        }
    }

    fn record_audit(&self, event: ComplianceAuditEvent) {
        let Some(path) = self.audit_log_path.as_deref() else {
            return;
        };

        if let Some(parent) = Path::new(path).parent() {
            if let Err(error) = create_dir_all(parent) {
                eprintln!("failed to create compliance log directory {parent:?}: {error}");
                return;
            }
        }

        let serialized = match serde_json::to_string(&event) {
            Ok(serialized) => serialized,
            Err(error) => {
                eprintln!("failed to serialize compliance audit event: {error}");
                return;
            }
        };

        match OpenOptions::new().create(true).append(true).open(path) {
            Ok(mut file) => {
                if let Err(error) = writeln!(file, "{serialized}") {
                    eprintln!("failed to write compliance audit record to {path}: {error}");
                }
            }
            Err(error) => {
                eprintln!("failed to open compliance audit log {path}: {error}");
            }
        }
    }
}

impl ChainalysisConfig {
    fn from_env() -> Result<Self, String> {
        let api_key = env::var("CHAINALYSIS_API_KEY").map_err(|_| {
            "CHAINALYSIS_API_KEY is required when COMPLIANCE_PROVIDER=chainalysis".to_string()
        })?;

        let rest_url = env::var("CHAINALYSIS_REST_URL")
            .unwrap_or_else(|_| "https://public.chainalysis.com/api/v1/address".to_string());
        let blocked_status = env::var("COMPLIANCE_BLOCKED_STATUS")
            .unwrap_or_else(|_| "BLOCKED".to_string());
        let timeout_ms = env::var("COMPLIANCE_TIMEOUT_MS")
            .ok()
            .and_then(|value| value.parse::<u64>().ok())
            .unwrap_or(1500);
        let fail_closed = parse_bool(
            env::var("COMPLIANCE_FAIL_CLOSED")
                .as_deref()
                .unwrap_or("true"),
        );

        Ok(Self {
            rest_url,
            api_key,
            blocked_status,
            timeout_ms,
            fail_closed,
        })
    }
}

fn parse_bool(value: &str) -> bool {
    matches!(
        value.to_lowercase().as_str(),
        "1" | "true" | "yes" | "y" | "on" | "enabled"
    )
}

fn parse_address_list(key: &str) -> Result<Vec<String>, String> {
    let raw = env::var(key).unwrap_or_default();
    Ok(raw
        .split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .filter_map(|address| {
            let normalized = normalize_address(address)?;
            Some(normalized)
        })
        .collect())
}

fn normalize_address(address: &str) -> Option<String> {
    let normalized = address.trim().to_lowercase();
    if normalized.starts_with("0x") && normalized.len() == 42 {
        return Some(normalized);
    }

    if normalized.len() == 40 && normalized.chars().all(|character| character.is_ascii_hexdigit()) {
        return Some(format!("0x{normalized}"));
    }

    None
}

fn is_valid_address(address: &str) -> bool {
    let normalized = address.trim().to_lowercase();
    normalized.len() == 42
        && normalized.starts_with("0x")
        && normalized.as_bytes()[2..].iter().all(|byte| {
            (*byte as char).is_ascii_hexdigit()
        })
}

fn extract_sanctions_status(value: &Value, blocked_status: &str) -> Option<bool> {
    let blocked = blocked_status.to_ascii_lowercase();

    if let Some(status) = value.get("sanctions").and_then(Value::as_str) {
        let status = status.trim().to_ascii_lowercase();
        if status == blocked {
            return Some(true);
        }
        if status == "clear" || status == "not_blocked" || status == "allowed" {
            return Some(false);
        }
    }

    if let Some(is_sanctioned) = value.get("is_sanctioned").and_then(Value::as_bool) {
        return Some(is_sanctioned);
    }

    if let Some(status) = value.get("status").and_then(Value::as_str) {
        let status = status.trim().to_ascii_lowercase();
        if status == blocked {
            return Some(true);
        }
        if status == "clear" || status == "not_blocked" || status == "allowed" {
            return Some(false);
        }
    }

    if let Some(risk_level) = value.get("riskLevel").and_then(Value::as_str) {
        match risk_level.to_ascii_lowercase().as_str() {
            "high" | "critical" => return Some(true),
            "low" => return Some(false),
            _ => {}
        }
    }

    if let Some(identifications) = value.get("identifications").and_then(Value::as_array) {
        return Some(!identifications.is_empty());
    }

    None
}

fn current_timestamp_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|time| time.as_millis())
        .unwrap_or(0)
}

async fn query_chainalysis(
    address: &str,
    config: &ChainalysisConfig,
) -> Result<ChainalysisResult, PaymentVerificationError> {
    let url = format!("{}/{}", config.rest_url.trim_end_matches("/"), address);
    let request = reqwest::Client::new()
        .get(&url)
        .header("X-API-KEY", config.api_key.as_str())
        .timeout(Duration::from_millis(config.timeout_ms));

    let response = request.send().await.map_err(|error| {
        PaymentVerificationError::ComplianceFailed(format!("chainalysis request failed: {error}"))
    })?;

    if response.status() != StatusCode::OK {
        let status = response.status();
        let body = response.text().await.unwrap_or_default();
        return Err(PaymentVerificationError::ComplianceFailed(format!(
            "chainalysis returned status {status}: {body}"
        )));
    }

    let body = response.text().await.map_err(|error| {
        PaymentVerificationError::ComplianceFailed(format!("failed to read chainalysis response: {error}"))
    })?;

    let body = body.trim();
    if body.is_empty() {
        return Err(PaymentVerificationError::ComplianceFailed(
            "empty response from chainalysis".to_string(),
        ));
    }

    let payload: Value = serde_json::from_str(body).map_err(|error| {
        PaymentVerificationError::ComplianceFailed(format!("invalid JSON from chainalysis: {error}"))
    })?;

    match extract_sanctions_status(&payload, &config.blocked_status) {
        Some(true) => Ok(ChainalysisResult::Denied("status matches blocked policy".to_string())),
        Some(false) => Ok(ChainalysisResult::Allowed),
        None => {
            if config.fail_closed {
                Ok(ChainalysisResult::Unknown(
                    "unrecognized chainalysis response format".to_string(),
                ))
            } else {
                Ok(ChainalysisResult::Allowed)
            }
        }
    }
}
