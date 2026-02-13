Patch 0001 add compliance gate before verify and settle in facilitator-local

DIFF:
*** Begin Patch
*** Update File: bbt-x402-facilitator/crates/x402-facilitator-local/src/facilitator_local.rs
@@
 use x402_types::proto;
 use x402_types::proto::PaymentVerificationError;
 use x402_types::scheme::{SchemeRegistry, X402SchemeFacilitatorError};
+
+// TODO: introduce ComplianceService trait and wiring into this type.
@@
 pub struct FacilitatorLocal<A> {
     handlers: A,
+    // compliance: Option<ComplianceService>,
 }
@@
     pub fn new(handlers: A) -> Self {
-        FacilitatorLocal { handlers }
+        FacilitatorLocal {
+            handlers,
+            // compliance: None,
+        }
     }
@@
     async fn verify(
         &self,
         request: &proto::VerifyRequest,
     ) -> Result<proto::VerifyResponse, Self::Error> {
+        // TODO: invoke compliance check here before handler verify.
         let handler = request
             .scheme_handler_slug()
             .and_then(|slug| self.handlers.by_slug(&slug))
             .ok_or(FacilitatorLocalError::Verification(
                 PaymentVerificationError::UnsupportedScheme.into(),
             ))?;
@@
     async fn settle(
         &self,
         request: &proto::SettleRequest,
     ) -> Result<proto::SettleResponse, Self::Error> {
+        // TODO: invoke compliance check again before settlement.
         let handler = request
             .scheme_handler_slug()
             .and_then(|slug| self.handlers.by_slug(&slug))
             .ok_or(FacilitatorLocalError::Verification(
                 PaymentVerificationError::UnsupportedScheme.into(),
*** End Patch
