Patch 0004 initial off-chain compliance screening (address-list mode)

DIFF:
*** Begin Patch
*** Update File: bbt-x402-facilitator/crates/x402-facilitator-local/src/compliance.rs
@@
+//! Compliance controls for facilitator-side request filtering.
+
+use std::env;
+
+use x402_types::proto::PaymentVerificationError;
+
+#[derive(Clone, Debug, Default)]
+pub struct ComplianceGate {
+    enabled: bool,
+    deny_list: Vec<String>,
+    allow_list: Vec<String>,
+}
+
+impl ComplianceGate {
+    pub fn disabled() -> Self { ... }
+    pub fn from_env() -> Result<Self, String> { ... }
+    pub fn validate(&self, payer: Option<&str>, payee: Option<&str>) -> Result<(), PaymentVerificationError> { ... }
+}
+
*** Update File: bbt-x402-facilitator/crates/x402-facilitator-local/src/facilitator_local.rs
@@
-// Existing x402-facilitator-local handler logic
+// Added compliance gate field and request pre-check hooks.
+// - `FacilitatorLocal` now stores `ComplianceGate`.
+// - `validate_parties` called before handler verify and settle.
+
*** Update File: bbt-x402-facilitator/facilitator/src/run.rs
@@
-    let facilitator = FacilitatorLocal::new(scheme_registry);
+    let compliance_gate = load_compliance_gate()?;
+    let facilitator = FacilitatorLocal::new_with_compliance(scheme_registry, compliance_gate);
*** End Patch
