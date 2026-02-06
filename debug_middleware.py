#!/usr/bin/env python3
"""Debug script to trace x402 SDK middleware initialization issue."""

import asyncio
import json
import httpx

FACILITATOR_URL = "https://exp-faci.etherlinkinsights.com"
NETWORK_ID = "eip155:42793"


async def test_facilitator_raw():
    """Test raw HTTP call to facilitator get_supported endpoint"""
    print("=" * 80)
    print("TEST 1: Raw HTTP Call to Facilitator")
    print("=" * 80)

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{FACILITATOR_URL}/api/supported")

        print(f"Status Code: {response.status_code}")
        print(f"Raw Response Text:\n{response.text}")

        try:
            data = json.loads(response.text)
            print(f"\nParsed JSON:\n{json.dumps(data, indent=2)}")

            if "kinds" in data:
                print(f"\nFound {len(data['kinds'])} kinds:")
                for i, kind in enumerate(data["kinds"]):
                    print(f"  [{i}] {json.dumps(kind, indent=4)}")
        except json.JSONDecodeError as e:
            print(f"JSON Parse Error: {e}")

    print("\n" + "=" * 80)


def test_sdk_client():
    """Test SDK HTTPFacilitatorClient"""
    print("\n" + "=" * 80)
    print("TEST 2: SDK HTTPFacilitatorClient")
    print("=" * 80)

    from x402.http import HTTPFacilitatorClient

    try:
        client = HTTPFacilitatorClient(config={"url": FACILITATOR_URL})

        print(f"Client created: {client}")
        print(f"Client config: {getattr(client, 'config', 'N/A')}")

        response = client.get_supported()
        print(f"\nget_supported() returned: {response}")
        print(f"Response type: {type(response)}")

        if hasattr(response, "kinds"):
            print(f"\nFound {len(response.kinds)} kinds:")
            for i, kind in enumerate(response.kinds):
                print(f"  [{i}] {kind}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 80)
    print("TEST 2: SDK HTTPFacilitatorClient")
    print("=" * 80)

    from x402.http import HTTPFacilitatorClient

    try:
        client = HTTPFacilitatorClient(config={"url": FACILITATOR_URL})

        print(f"Client created: {client}")
        print(f"Client config: {getattr(client, 'config', 'N/A')}")

        response = await client.get_supported()
        print(f"\nget_supported() returned: {response}")
        print(f"Response type: {type(response)}")

        if hasattr(response, "kinds"):
            print(f"\nFound {len(response.kinds)} kinds:")
            for i, kind in enumerate(response.kinds):
                print(f"  [{i}] {kind}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 80)


async def test_resource_server():
    """Test x402ResourceServer initialization"""
    print("\n" + "=" * 80)
    print("TEST 3: x402ResourceServer with register_exact_evm_server")
    print("=" * 80)

    from x402.http import HTTPFacilitatorClient
    from x402.server import x402ResourceServer
    from x402.mechanisms.evm.exact.register import register_exact_evm_server

    try:
        facilitator_client = HTTPFacilitatorClient(config={"url": FACILITATOR_URL})
        print(f"✓ HTTPFacilitatorClient created")

        resource_server = x402ResourceServer(facilitator_client)
        print(f"✓ x402ResourceServer created: {resource_server}")

        register_exact_evm_server(resource_server, NETWORK_ID)
        print(f"✓ register_exact_evm completed for {NETWORK_ID}")

        print(f"\nResource server details:")
        print(f"  Type: {type(resource_server)}")
        print(
            f"  Attributes: {[a for a in dir(resource_server) if not a.startswith('_')]}"
        )

        return resource_server

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return None

    print("\n" + "=" * 80)


async def test_middleware_init():
    """Test PaymentMiddlewareASGI initialization"""
    print("\n" + "=" * 80)
    print("TEST 4: PaymentMiddlewareASGI initialization")
    print("=" * 80)

    from fastapi import FastAPI
    from x402.http import HTTPFacilitatorClient
    from x402.server import x402ResourceServer
    from x402.mechanisms.evm.exact.register import register_exact_evm_server
    from x402.http.middleware.fastapi import PaymentMiddlewareASGI

    routes_config = {
        "GET /api/weather": {
            "accepts": [
                {
                    "scheme": "exact",
                    "price": "$0.01",
                    "network": NETWORK_ID,
                    "pay_to": "0x81C54CB7690016b2b0c3017a4991783964601bd9",
                    "token": "0x7EfE4bdd11237610bcFca478937658bE39F8dfd6",
                }
            ],
            "description": "Get current weather data",
            "mime_type": "application/json",
        },
    }

    try:
        print("Step 1: Creating facilitator_client...")
        facilitator_client = HTTPFacilitatorClient(config={"url": FACILITATOR_URL})
        print("✓ HTTPFacilitatorClient created")

        print("\nStep 2: Creating resource_server...")
        resource_server = x402ResourceServer(facilitator_client)
        print("✓ x402ResourceServer created")

        print("\nStep 3: Calling register_exact_evm_server...")
        register_exact_evm_server(resource_server, NETWORK_ID)
        print(f"✓ register_exact_evm completed for {NETWORK_ID}")

        print("\nStep 4: Creating FastAPI app...")
        app = FastAPI()
        print("✓ FastAPI app created")

        print("\nStep 5: Inspecting PaymentMiddlewareASGI class...")
        middleware_class = PaymentMiddlewareASGI
        print(f"  Class: {middleware_class}")
        print(f"  Base classes: {middleware_class.__bases__}")

        print("\nStep 6: Adding middleware via FastAPI add_middleware...")
        app.add_middleware(
            PaymentMiddlewareASGI, routes=routes_config, server=resource_server
        )
        print("✓ Middleware added successfully")

    except Exception as e:
        print(f"\n✗ FAILED during middleware instantiation")
        print(f"Error: {e}")
        print(f"Error type: {type(e).__name__}")

        import traceback

        print("\nFull traceback:")
        traceback.print_exc()

    print("\n" + "=" * 80)
    print("TEST 4: PaymentMiddlewareASGI initialization")
    print("=" * 80)

    from x402.http import HTTPFacilitatorClient
    from x402.server import x402ResourceServer
    from x402.mechanisms.evm.exact.register import register_exact_evm_server
    from x402.http.middleware.fastapi import PaymentMiddlewareASGI

    routes_config = {
        "GET /api/weather": {
            "accepts": [
                {
                    "scheme": "exact",
                    "price": "$0.01",
                    "network": NETWORK_ID,
                    "pay_to": "0x81C54CB7690016b2b0c3017a4991783964601bd9",
                    "token": "0x7EfE4bdd11237610bcFca478937658bE39F8dfd6",
                }
            ],
            "description": "Get current weather data",
            "mime_type": "application/json",
        },
    }

    try:
        print("Step 1: Creating facilitator_client...")
        facilitator_client = HTTPFacilitatorClient(config={"url": FACILITATOR_URL})
        print("✓ HTTPFacilitatorClient created")

        print("\nStep 2: Creating resource_server...")
        resource_server = x402ResourceServer(facilitator_client)
        print("✓ x402ResourceServer created")

        print("\nStep 3: Calling register_exact_evm_server...")
        register_exact_evm_server(resource_server, NETWORK_ID)
        print(f"✓ register_exact_evm completed for {NETWORK_ID}")

        print("\nStep 4: Creating PaymentMiddlewareASGI instance...")
        middleware_class = PaymentMiddlewareASGI
        print(f"  Class: {middleware_class}")
        print(
            f"  Class attributes: {[a for a in dir(middleware_class) if not a.startswith('_')]}"
        )

        middleware = middleware_class(routes=routes_config, server=resource_server)
        print("✓ PaymentMiddlewareASGI instance created")
        print(f"  Middleware object: {middleware}")

    except Exception as e:
        print(f"\n✗ FAILED during middleware instantiation")
        print(f"Error: {e}")
        print(f"Error type: {type(e).__name__}")

        import traceback

        print("\nFull traceback:")
        traceback.print_exc()

    print("\n" + "=" * 80)


def test_middleware_with_fastapi():
    """Test adding middleware to FastAPI app (like bbt_storefront.py)"""
    print("\n" + "=" * 80)
    print("TEST 5: PaymentMiddlewareASGI with FastAPI app")
    print("=" * 80)

    from fastapi import FastAPI
    from x402.http import HTTPFacilitatorClient
    from x402.server import x402ResourceServer
    from x402.mechanisms.evm.exact.register import register_exact_evm_server
    from x402.http.middleware.fastapi import PaymentMiddlewareASGI

    routes_config = {
        "GET /api/test": {
            "accepts": [
                {
                    "scheme": "exact",
                    "price": "$0.01",
                    "network": NETWORK_ID,
                    "pay_to": "0x81C54CB7690016b2b0c3017a4991783964601bd9",
                    "token": "0x7EfE4bdd11237610bcFca478937658bE39F8dfd6",
                }
            ],
            "description": "Test endpoint",
            "mime_type": "application/json",
        },
    }

    try:
        print("Step 1: Creating FastAPI app...")
        app = FastAPI()
        print("✓ FastAPI app created")

        print("\nStep 2: Setting up x402 infrastructure...")
        facilitator_client = HTTPFacilitatorClient(config={"url": FACILITATOR_URL})
        resource_server = x402ResourceServer(facilitator_client)
        register_exact_evm_server(resource_server, NETWORK_ID)
        print("✓ x402 infrastructure set up")

        print("\nStep 3: Adding PaymentMiddlewareASGI...")
        app.add_middleware(
            PaymentMiddlewareASGI, routes=routes_config, server=resource_server
        )
        print("✓ Middleware added to FastAPI app")

        print("\nStep 4: Checking app middleware stack...")
        print(f"  App middleware count: {len(app.user_middleware)}")
        for i, mw in enumerate(app.user_middleware):
            print(f"  [{i}] {mw}")

        print("\n✅ All steps completed successfully!")

    except Exception as e:
        print(f"\n✗ FAILED")
        print(f"Error: {e}")
        print(f"Error type: {type(e).__name__}")

        import traceback

        print("\nFull traceback:")
        traceback.print_exc()

    print("\n" + "=" * 80)
    print("TEST 5: PaymentMiddlewareASGI with FastAPI app")
    print("=" * 80)

    from fastapi import FastAPI
    from x402.http import HTTPFacilitatorClient
    from x402.server import x402ResourceServer
    from x402.mechanisms.evm.exact.register import register_exact_evm_server
    from x402.http.middleware.fastapi import PaymentMiddlewareASGI

    routes_config = {
        "GET /api/test": {
            "accepts": [
                {
                    "scheme": "exact",
                    "price": "$0.01",
                    "network": NETWORK_ID,
                    "pay_to": "0x81C54CB7690016b2b0c3017a4991783964601bd9",
                    "token": "0x7EfE4bdd11237610bcFca478937658bE39F8dfd6",
                }
            ],
            "description": "Test endpoint",
            "mime_type": "application/json",
        },
    }

    try:
        print("Step 1: Creating FastAPI app...")
        app = FastAPI()
        print("✓ FastAPI app created")

        print("\nStep 2: Setting up x402 infrastructure...")
        facilitator_client = HTTPFacilitatorClient(config={"url": FACILITATOR_URL})
        resource_server = x402ResourceServer(facilitator_client)
        register_exact_evm_server(resource_server, NETWORK_ID)
        print("✓ x402 infrastructure set up")

        print("\nStep 3: Adding PaymentMiddlewareASGI...")
        app.add_middleware(
            PaymentMiddlewareASGI, routes=routes_config, server=resource_server
        )
        print("✓ Middleware added to FastAPI app")

        print("\nStep 4: Checking app middleware stack...")
        print(f"  App middleware count: {len(app.user_middleware)}")
        for i, mw in enumerate(app.user_middleware):
            print(f"  [{i}] {mw}")

        print("\n✅ All steps completed successfully!")

    except Exception as e:
        print(f"\n✗ FAILED")
        print(f"Error: {e}")
        print(f"Error type: {type(e).__name__}")

        import traceback

        print("\nFull traceback:")
        traceback.print_exc()

    print("\n" + "=" * 80)


async def main():
    """Run all debug tests"""
    print("\n" * 2)
    print("*" * 80)
    print("X402 SDK Middleware Initialization Debug")
    print("*" * 80)
    print(f"Facilitator URL: {FACILITATOR_URL}")
    print(f"Target Network: {NETWORK_ID}")
    print("*" * 80)

    await test_facilitator_raw()
    await test_sdk_client()
    await test_resource_server()
    await test_middleware_init()
    await test_middleware_with_fastapi()

    print("\n" * 2)
    print("*" * 80)
    print("Debug Tests Complete")
    print("*" * 80)


if __name__ == "__main__":
    asyncio.run(main())
