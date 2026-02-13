//! Compliance controls for facilitator-side request filtering.

use reqwest::StatusCode;
use serde_json::Value;
use std::env;
use std::time::Duration;
use x402_types::proto::PaymentVerificationError;

#[derive(Clone, Debug)]
pub struct ComplianceGate {
    enabled: bool,
    deny_list: Vec<String>,
    allow_list: Vec<String>,
    provider: ComplianceProvider,
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

        Ok(Self {
            enabled,
            deny_list,
            allow_list,
            provider,
        })
    }

    pub async fn validate(&self, payer: Option<&str>, payee: Option<&str>) -> Result<(), PaymentVerificationError> {
        if !self.enabled {
            return Ok(());
        }

        if let Some(payer) = payer {
            self.validate_party("payer", payer).await?;
        }
        if let Some(payee) = payee {
            self.validate_party("payee", payee).await?;
        }

        Ok(())
    }

    async fn validate_party(&self, role: &str, raw_address: &str) -> Result<(), PaymentVerificationError> {
        let address = normalize_address(raw_address)
            .ok_or_else(|| PaymentVerificationError::ComplianceFailed(format!("{role} has an invalid address format")))?;

        if self.deny_list.iter().any(|denied| denied == &address) {
            return Err(PaymentVerificationError::ComplianceFailed(format!(
                "{role} is denied by compliance policy: {address}"
            )));
        }

        if !self.allow_list.is_empty() && !self.allow_list.iter().any(|allowed| allowed == &address) {
            return Err(PaymentVerificationError::ComplianceFailed(format!(
                "{role} is not in compliance allow-list"
            )));
        }

        match &self.provider {
            ComplianceProvider::Lists => Ok(()),
            ComplianceProvider::Chainalysis(config) => {
                let status = query_chainalysis(&address, config).await?;
                match status {
                    ChainalysisResult::Allowed => Ok(()),
                    ChainalysisResult::Denied(reason) => {
                        Err(PaymentVerificationError::ComplianceFailed(format!(
                            "{role} failed provider screening: {reason}"
                        )))
                    }
                    ChainalysisResult::Unknown(reason) => {
                        if config.fail_closed {
                            Err(PaymentVerificationError::ComplianceFailed(format!(
                                "{role} screening result unresolved: {reason}"
                            )))
                        } else {
                            Ok(())
                        }
                    }
                }
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
        .split(",")
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
