import os
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

if os.getenv("ENABLE_UNSAFE_MANUAL_STOREFRONT", "0") != "1":
    raise RuntimeError(
        "manual_storefront.py is intentionally unsafe for payments. "
        "Set ENABLE_UNSAFE_MANUAL_STOREFRONT=1 only for isolated demos."
    )

app = FastAPI(title="BBT Storefront Manual")

@app.get("/")
def root():
    return {"status": "running", "payment_gateway": "manual x402 implementation"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/api/weather")
async def weather(request: Request):
    payment_signature = request.headers.get("Payment-Signature") or request.headers.get(
        "payment-signature"
    )
    
    if not payment_signature:
        return JSONResponse(
            status_code=402,
            content={"error": "Payment required"},
            headers={
                "Payment-Required": "eyJuZXR3b3JrIjoiZWlwMTU1OjQyNzkzIiwic2NoZW1lIjoiZXhhY3QiLCJwcmljZSI6IiQwLjAxIiwicGF5X3RvIjoiMHg4MUM1NENCNzY5MDAxNmIyYjBjMzAxN2E0OTkxNzgzOTY0NjAxYmQ5In0="
            }
        )
    
    return {
        "location": "Singapore",
        "temperature": 32,
        "condition": "Sunny",
        "payment_verified": True,
        "payment_signature_preview": payment_signature[:30] + "..." 
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
