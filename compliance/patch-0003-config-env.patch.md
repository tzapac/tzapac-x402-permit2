Patch 0003 compliance env values and defaults in docs

DIFF:
*** Begin Patch
*** Update File: .env.example
@@
 PUBLIC_BASE_URL=http://localhost:9091
 EXPLORER_TX_BASE_URL=https://explorer.etherlink.com/tx
 MAX_PAYMENT_SIGNATURE_B64_BYTES=16384
 MAX_SETTLE_RESPONSE_BYTES=65536
+
+# Compliance screening
+COMPLIANCE_ENABLED=false
+COMPLIANCE_PROVIDER=chainalysis
+CHAINALYSIS_REST_URL=https://api.chainalysis.com/api/v2/address
+COMPLIANCE_BLOCKED_STATUS=BLOCKED
+COMPLIANCE_TIMEOUT_MS=1500
+COMPLIANCE_CACHE_TTL_SECONDS=120
+COMPLIANCE_FAIL_CLOSED=true
+COMPLIANCE_CHECK_IN_SETTLE=true
*** End Patch
