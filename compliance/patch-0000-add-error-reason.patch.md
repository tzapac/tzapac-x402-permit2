Patch 0000 protocol-level compliance rejection reason

DIFF:
*** Begin Patch
*** Update File: bbt-x402-facilitator/crates/x402-types/src/proto/mod.rs
@@
 pub enum PaymentVerificationError {
+    ComplianceFailed(String),
@@
 impl AsPaymentProblem for PaymentVerificationError {
     fn as_payment_problem(&self) -> PaymentProblem {
         let error_reason = match self {
+            PaymentVerificationError::ComplianceFailed(_) => ErrorReason::ComplianceFailed,
             PaymentVerificationError::InvalidFormat(_) => ErrorReason::InvalidFormat,
@@
 }
@@
 pub enum ErrorReason {
+    ComplianceFailed,
