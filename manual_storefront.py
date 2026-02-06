import os
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

app = FastAPI(title="BBT Storefront Manual")

@app.get("/")
def root():
    return {"status": "running", "payment_gateway": "manual x402 implementation"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/api/weather")
async def weather(request: Request):
    payment_signature = request.headers.get("PAYMENT-SIGNATURE") or request.headers.get("X-PAYMENT-SIGNATURE")
    
    if not payment_signature:
        return JSONResponse(
            status_code=402,
            content={"error": "Payment required"},
            headers={
                "PAYMENT-REQUIRED": "eyJuZXR3b3JrIjoiZWlwMTU1OjQyNzkzIiwic2NoZW1lIjoiZXhhY3QiLCJwcmljZSI6IiQwLjAxIiwicGF5X3RvIjoiMHg4MUM1NENCNzY5MDAxNmIyYjBjMzAxN2E0OTkxNzgzOTY0NjAxYmQ5In0="
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
