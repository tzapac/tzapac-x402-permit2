Patch 0002 route-level integration in binary startup

DIFF:
*** Begin Patch
*** Update File: bbt-x402-facilitator/facilitator/src/run.rs
@@
 use x402_facilitator_local::util::SigDown;
 use x402_facilitator_local::{FacilitatorLocal, handlers};
@@
-    let facilitator = FacilitatorLocal::new(scheme_registry);
+    // TODO: load compliance config from env and inject service.
+    let facilitator = FacilitatorLocal::new(scheme_registry);
     let axum_state = Arc::new(facilitator);
*** End Patch
