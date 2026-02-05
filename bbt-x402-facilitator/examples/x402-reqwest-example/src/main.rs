use alloy_signer_local::PrivateKeySigner;
use dotenvy::dotenv;
use reqwest::Client;
use std::env;
use std::sync::Arc;
use x402_chain_eip155::{V1Eip155ExactClient, V2Eip155ExactClient};
use x402_reqwest::{ReqwestWithPayments, ReqwestWithPaymentsBuild, X402Client};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    dotenv().ok();

    let mut x402_client = X402Client::new();
    // Register eip155 "exact" scheme
    {
        let signer: Option<PrivateKeySigner> = env::var("EVM_PRIVATE_KEY")
            .ok()
            .and_then(|key| key.parse().ok());
        if let Some(signer) = signer {
            println!("Using EVM signer address: {:?}", signer.address());
            let signer = Arc::new(signer);
            x402_client = x402_client
                .register(V1Eip155ExactClient::new(signer.clone()))
                .register(V2Eip155ExactClient::new(signer));
            println!("Enabled eip155 exact scheme")
        }
    };

    let http_client = Client::new().with_payments(x402_client).build();

    let response = http_client
        .get("http://localhost:3000/protected-route")
        .send()
        .await?;

    println!("Response: {:?}", response.text().await?);

    Ok(())
}
