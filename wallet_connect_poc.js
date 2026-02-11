    // --- CONSTANTS ---
    const BBT_ADDRESS = "0x7EfE4bdd11237610bcFca478937658bE39F8dfd6";
    const PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3";
    // Etherlink-deployed x402 exact Permit2 proxy (Coinbase-aligned).
    const DEFAULT_X402_EXACT_PERMIT2_PROXY_ADDRESS = "0xB6FD384A0626BfeF85f3dBaf5223Dd964684B09E";
    const ETHERLINK_CHAIN_ID = 42793;
    const ETHERLINK_CHAIN_ID_HEX = "0xA739";
    const RPC_URL = "https://rpc.bubbletez.com";
    const IS_LOCAL_PAGE = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
    const DEFAULT_FACILITATOR_URL = IS_LOCAL_PAGE ? "http://localhost:9090" : "https://exp-faci.bubbletez.com";
    const DEFAULT_STORE_URL = IS_LOCAL_PAGE ? "http://localhost:9091/api/weather" : "https://exp-store.bubbletez.com/api/weather";
    const ETHERS_CDN_URLS = [
        "https://cdn.jsdelivr.net/npm/ethers@6.13.4/dist/ethers.umd.min.js",
        "https://unpkg.com/ethers@6.13.4/dist/ethers.umd.min.js"
    ];

    // --- STATE ---
    let provider, signer, bbtContract;
    let userAddress;
    let gasPayerMode = "facilitator";
    let tokenDetailsOpen = false;
    let facilitatorOnline = null;
    let facilitatorPollTimer = null;
    let catalogItems = [];

    // --- ABI ---
    const ERC20_ABI = [
        "function name() view returns (string)",
        "function symbol() view returns (string)",
        "function decimals() view returns (uint8)",
        "function balanceOf(address) view returns (uint256)",
        "function allowance(address, address) view returns (uint256)",
        "function approve(address, uint256) returns (bool)"
    ];

    // --- UI ELEMENTS ---
    const ui = {
        statusDot: document.getElementById('status-dot'),
        statusText: document.getElementById('status-text'),
        approveBtn: document.getElementById('approve-btn'),
        healthBtn: document.getElementById('health-btn'),
        facilitatorInput: document.getElementById('facilitator-input'),
        spenderInput: document.getElementById('spender-input'),
        storeInput: document.getElementById('store-input'),
        catalogRow: document.getElementById('catalog-row'),
        catalogSelect: document.getElementById('catalog-select'),
        requirementsBtn: document.getElementById('requirements-btn'),
        payBtn: document.getElementById('pay-btn'),
        network: document.getElementById('network-display'),
        account: document.getElementById('account-display'),
        balance: document.getElementById('balance-display'),
        allowance: document.getElementById('allowance-display'),
        permit2AllowanceRow: document.getElementById('permit2-allowance-row'),
        permit2Allowance: document.getElementById('permit2-allowance-display'),
        permit2Expiration: document.getElementById('permit2-expiration-display'),
        permit2Nonce: document.getElementById('permit2-nonce-display'),
        amount: document.getElementById('amount-display'),
        payTo: document.getElementById('payto-display'),
        tokenSection: document.getElementById('token-section'),
        tokenToggleBtn: document.getElementById('token-toggle-btn'),
        gasFacilitatorBtn: document.getElementById('gas-facilitator-btn'),
        disclaimerOverlay: document.getElementById('disclaimer-overlay'),
        disclaimerOkBtn: document.getElementById('disclaimer-ok-btn'),
        console: document.getElementById('console-output')
    };

    const tabButtons = Array.from(document.querySelectorAll('.tab-button'));
    const tabPanels = Array.from(document.querySelectorAll('.tab-panel'));

    // --- LOGGING ---
    function log(msg, type = 'info') {
        const div = document.createElement('div');
        div.className = `log-entry log-${type}`;
        div.innerText = `> ${msg}`;
        ui.console.appendChild(div);
        ui.console.scrollTop = ui.console.scrollHeight;
    }

    // --- INITIALIZATION ---
    function loadScript(src) {
        return new Promise((resolve, reject) => {
            const script = document.createElement("script");
            script.src = src;
            script.async = true;
            script.onload = () => resolve(true);
            script.onerror = () => reject(new Error(`Failed to load ${src}`));
            document.head.appendChild(script);
        });
    }

    async function ensureEthers() {
        if (typeof ethers !== "undefined") {
            return true;
        }

        for (const src of ETHERS_CDN_URLS) {
            try {
                log(`LOADING ETHERS: ${src}`, "info");
                await loadScript(src);
                if (typeof ethers !== "undefined") {
                    log("ETHERS LOADED", "success");
                    return true;
                }
            } catch (err) {
                log(`ETHERS LOAD FAILED: ${err.message}`, "error");
            }
        }

        return false;
    }

    async function init() {
        if (!ui.facilitatorInput.value) {
            ui.facilitatorInput.value = DEFAULT_FACILITATOR_URL;
        }
        if (!ui.storeInput.value) {
            ui.storeInput.value = DEFAULT_STORE_URL;
        }
        if (!ui.spenderInput.value) {
            ui.spenderInput.value = DEFAULT_X402_EXACT_PERMIT2_PROXY_ADDRESS;
        }

        ui.approveBtn.addEventListener('click', approvePermit2);
        ui.healthBtn.addEventListener('click', checkFacilitatorHealth);
        ui.requirementsBtn.addEventListener('click', fetchPaymentRequirements);
        ui.payBtn.addEventListener('click', signAndPay);
        ui.tokenToggleBtn.addEventListener('click', toggleTokenDetails);
        ui.gasFacilitatorBtn.addEventListener('click', () => setGasPayerMode('facilitator'));
        ui.catalogSelect.addEventListener('change', onCatalogSelectionChanged);
        ui.storeInput.addEventListener('change', onStoreUrlChanged);
        ui.storeInput.addEventListener('blur', onStoreUrlChanged);
        ui.disclaimerOkBtn.addEventListener('click', () => {
            ui.disclaimerOverlay.classList.add('hidden');
        });

        tabButtons.forEach((button) => {
            button.addEventListener('click', () => setActiveTab(button.dataset.tab));
        });

        setActiveTab('demo');

        setGasPayerMode('facilitator');
        updateTokenToggle();
        await refreshCatalog();

        startFacilitatorPolling();

        const ethersReady = await ensureEthers();
        if (!ethersReady) {
            log("CRITICAL: Ethers.js library not loaded. Check internet connection or CDN.", "error");
            disableWalletActions();
            return;
        }

        if (!window.ethereum) {
            log("METAMASK NOT DETECTED", "error");
            disableWalletActions();
            return;
        }

        // Auto-connect if already authorized
        const accounts = await window.ethereum.request({ method: 'eth_accounts' });
        if (accounts.length > 0) {
            connectWallet();
        }

        window.ethereum.on('chainChanged', () => window.location.reload());
        window.ethereum.on('accountsChanged', () => window.location.reload());
    }

    function setActiveTab(tabName) {
        tabButtons.forEach((button) => {
            button.classList.toggle('active', button.dataset.tab === tabName);
        });
        tabPanels.forEach((panel) => {
            panel.classList.toggle('hidden', panel.dataset.panel !== tabName);
        });
    }

    function setFacilitatorStatus(isOnline) {
        if (facilitatorOnline === isOnline) {
            return;
        }
        facilitatorOnline = isOnline;
        ui.statusDot.classList.toggle('active', isOnline);
        ui.statusText.innerText = isOnline ? "ONLINE" : "OFFLINE";
    }

    function hasSupportedNetwork(body) {
        if (!body) {
            return false;
        }
        const text = typeof body === "string" ? body : JSON.stringify(body);
        return text.includes("eip155:42793") || text.includes("42793");
    }

    async function pollFacilitatorSupported() {
        const base = getFacilitatorUrl();
        if (!base) {
            setFacilitatorStatus(false);
            return;
        }
        const url = `${base}/supported`;
        try {
            const resp = await fetch(url, { cache: "no-store" });
            const contentType = resp.headers.get("content-type") || "";
            const body = contentType.includes("application/json") ? await resp.json() : await resp.text();
            if (!resp.ok) {
                throw new Error(`HTTP ${resp.status}`);
            }
            setFacilitatorStatus(hasSupportedNetwork(body));
        } catch (err) {
            setFacilitatorStatus(false);
        }
    }

    function startFacilitatorPolling() {
        pollFacilitatorSupported();
        if (facilitatorPollTimer) {
            clearInterval(facilitatorPollTimer);
        }
        facilitatorPollTimer = setInterval(pollFacilitatorSupported, 10000);
        ui.facilitatorInput.addEventListener('change', pollFacilitatorSupported);
    }

    // --- CONNECT WALLET ---
    async function connectWallet() {
        try {
            log("INITIALIZING CONNECTION...", "info");
            provider = new ethers.BrowserProvider(window.ethereum);
            
            await provider.send("eth_requestAccounts", []);
            signer = await provider.getSigner();
            userAddress = await signer.getAddress();

            log(`CONNECTED: ${userAddress.slice(0,6)}...${userAddress.slice(-4)}`, "success");
            ui.account.innerText = userAddress;

            await checkNetwork();
        } catch (err) {
            log(`CONNECTION FAILED: ${err.message}`, "error");
        }
    }

    async function ensureWalletConnected() {
        if (signer && userAddress) {
            return true;
        }
        if (!window.ethereum) {
            log("METAMASK NOT DETECTED", "error");
            return false;
        }
        await connectWallet();
        return Boolean(signer && userAddress);
    }

    function disableWalletActions() {
        ui.approveBtn.disabled = true;
        ui.payBtn.disabled = true;
    }

    function updateTokenToggle() {
        ui.tokenToggleBtn.innerText = tokenDetailsOpen
            ? "HIDE TOKEN DETAILS"
            : "SHOW TOKEN DETAILS";
    }

    async function toggleTokenDetails() {
        tokenDetailsOpen = !tokenDetailsOpen;
        if (tokenDetailsOpen) {
            const ready = await ensureWalletConnected();
            if (!ready) {
                tokenDetailsOpen = false;
                updateTokenToggle();
                return;
            }
            if (!bbtContract) {
                await loadTokenData();
            }
            ui.tokenSection.classList.remove('hidden');
        } else {
            ui.tokenSection.classList.add('hidden');
        }
        updateTokenToggle();
    }

    function setGasPayerMode(mode) {
        gasPayerMode = 'facilitator';
        ui.gasFacilitatorBtn.classList.add('active');
        if (mode !== 'facilitator') {
            log("ONLY FACILITATOR GAS MODE IS ENABLED IN TZAPAC-ALIGNED FLOW", "info");
        }
        log("GAS PAYER: FACILITATOR", "info");
    }

    // --- CHECK NETWORK ---
    async function checkNetwork() {
        const network = await provider.getNetwork();
        const chainId = Number(network.chainId);

        if (chainId !== ETHERLINK_CHAIN_ID) {
            log(`WRONG NETWORK DETECTED (ID: ${chainId})`, "error");
            ui.network.innerText = "WRONG NETWORK";
            ui.network.style.color = "var(--error-color)";
            await switchNetwork();
        } else {
            ui.network.innerText = "ETHERLINK MAINNET";
            ui.network.style.color = "var(--accent-color)";
            log("NETWORK VERIFIED: ETHERLINK", "success");
            await loadTokenData();
        }
    }

    // --- SWITCH NETWORK ---
    async function switchNetwork() {
        try {
            log("ATTEMPTING NETWORK SWITCH...", "info");
            await window.ethereum.request({
                method: 'wallet_switchEthereumChain',
                params: [{ chainId: ETHERLINK_CHAIN_ID_HEX }],
            });
            window.location.reload();
        } catch (switchError) {
            // This error code indicates that the chain has not been added to MetaMask.
            if (switchError.code === 4902) {
                log("NETWORK NOT FOUND. ADDING ETHERLINK...", "info");
                try {
                    await window.ethereum.request({
                        method: 'wallet_addEthereumChain',
                        params: [
                            {
                                chainId: ETHERLINK_CHAIN_ID_HEX,
                                chainName: 'Etherlink Mainnet',
                                rpcUrls: [RPC_URL],
                                nativeCurrency: {
                                    name: 'Tezos',
                                    symbol: 'XTZ',
                                    decimals: 18
                                },
                                blockExplorerUrls: ['https://explorer.etherlink.com/']
                            },
                        ],
                    });
                    window.location.reload();
                } catch (addError) {
                    log(`FAILED TO ADD NETWORK: ${addError.message}`, "error");
                }
            } else {
                log(`FAILED TO SWITCH NETWORK: ${switchError.message}`, "error");
            }
        }
    }

    // --- LOAD TOKEN DATA ---
    async function loadTokenData() {
        try {
            if (!signer || !userAddress) {
                return;
            }
            bbtContract = new ethers.Contract(BBT_ADDRESS, ERC20_ABI, signer);

            const decimals = await bbtContract.decimals();
            const balance = await bbtContract.balanceOf(userAddress);
            const erc20Allowance = await bbtContract.allowance(userAddress, PERMIT2_ADDRESS);

            ui.balance.innerText = ethers.formatUnits(balance, decimals);
            ui.allowance.innerText = ethers.formatUnits(erc20Allowance, decimals);

            const spender = getSpenderForPermit2();
            if (spender) {
                const permit2Abi = [
                    "function allowance(address owner,address token,address spender) view returns (uint160 amount,uint48 expiration,uint48 nonce)"
                ];
                const permit2 = new ethers.Contract(PERMIT2_ADDRESS, permit2Abi, provider);
                const tokenAddress = getPermit2Token();
                const allowanceData = await permit2.allowance(userAddress, tokenAddress, spender);
                const permit2Amount = allowanceData[0];
                const permit2Expiration = allowanceData[1];
                const permit2Nonce = allowanceData[2];

                if (permit2Amount > 0n) {
                    ui.permit2AllowanceRow.classList.remove('hidden');
                    ui.permit2Allowance.innerText = ethers.formatUnits(permit2Amount, decimals);
                } else {
                    ui.permit2AllowanceRow.classList.add('hidden');
                    ui.permit2Allowance.innerText = "--";
                }
                ui.permit2Expiration.innerText = formatExpiry(Number(permit2Expiration));
                ui.permit2Nonce.innerText = permit2Nonce.toString();
            } else {
                ui.permit2AllowanceRow.classList.add('hidden');
                ui.permit2Allowance.innerText = "--";
                ui.permit2Expiration.innerText = "--";
                ui.permit2Nonce.innerText = "--";
            }

            updateApproveButton(erc20Allowance);

            if (tokenDetailsOpen) {
                ui.tokenSection.classList.remove('hidden');
            }
            ui.approveBtn.classList.remove('hidden');

            log("TOKEN DATA LOADED", "success");
        } catch (err) {
            log(`FAILED TO LOAD TOKEN DATA: ${err.message}`, "error");
        }
    }

    // --- APPROVE PERMIT2 ---
    async function approvePermit2() {
        const ready = await ensureWalletConnected();
        if (!ready) return;
        if (!bbtContract) {
            await loadTokenData();
        }
        if (!bbtContract) return;

        try {
            ui.approveBtn.disabled = true;
            ui.approveBtn.innerText = "SIGNING...";
            log("INITIATING APPROVAL TRANSACTION...", "info");

            const requiredAmount = getRequiredAmount();
            if (!requiredAmount || requiredAmount <= 0n) {
                log("GET PAYMENT REQUIREMENTS FIRST TO APPROVE THE EXACT AMOUNT.", "error");
                ui.approveBtn.disabled = false;
                ui.approveBtn.innerText = "GET PAYMENT FIRST";
                return;
            }

            const tx = await bbtContract.approve(PERMIT2_ADDRESS, requiredAmount);
            log("REQUESTED APPROVAL AMOUNT: " + requiredAmount.toString(), "info");
            
            log(`TX SENT: ${tx.hash}`, "info");
            ui.approveBtn.innerText = "PENDING...";

            await tx.wait();
            
            log("TRANSACTION CONFIRMED", "success");
            
            await loadTokenData(); // Refresh UI
        } catch (err) {
            log(`APPROVAL FAILED: ${err.message}`, "error");
            ui.approveBtn.disabled = false;
            ui.approveBtn.innerText = "APPROVE PERMIT2";
        }
    }

    // --- FACILITATOR LINKS ---
    function isLocalHostname(hostname) {
        const host = (hostname || "").toLowerCase();
        return host === "localhost" || host === "127.0.0.1" || host === "::1" || host.endsWith(".local");
    }

    function normalizeEndpointUrl(raw, fallback) {
        const candidate = (raw || "").trim() || fallback;
        if (!candidate) {
            return null;
        }
        try {
            const url = new URL(candidate);
            if (url.protocol !== "http:" && url.protocol !== "https:") {
                return null;
            }
            const isLocal = isLocalHostname(url.hostname);
            if (!isLocal && url.protocol !== "https:") {
                return null;
            }
            if (window.location.protocol === "https:" && url.protocol === "http:" && !isLocal) {
                return null;
            }
            return url.toString().replace(/\/$/, "");
        } catch (err) {
            return null;
        }
    }

    function getFacilitatorUrl() {
        return normalizeEndpointUrl(ui.facilitatorInput.value, DEFAULT_FACILITATOR_URL);
    }

    async function checkFacilitatorHealth() {
        const base = getFacilitatorUrl();
        if (!base) {
            setFacilitatorStatus(false);
            log("INVALID FACILITATOR URL. USE HTTPS (OR HTTP FOR LOCALHOST).", "error");
            return;
        }
        const url = `${base}/health`;
        try {
            log(`CHECKING FACILITATOR: ${url}`, "info");
            const resp = await fetch(url);
            const contentType = resp.headers.get("content-type") || "";
            const body = contentType.includes("application/json") ? await resp.json() : await resp.text();
            if (!resp.ok) {
                throw new Error(`HTTP ${resp.status}`);
            }
            log("FACILITATOR HEALTHY", "success");
            setFacilitatorStatus(true);
            if (!ui.spenderInput.value) {
                ui.spenderInput.value = DEFAULT_X402_EXACT_PERMIT2_PROXY_ADDRESS;
                log(`SPENDER DEFAULTED TO X402 PROXY: ${DEFAULT_X402_EXACT_PERMIT2_PROXY_ADDRESS}`, "success");
            }
            if (body && typeof body === "object") {
                const signerAddress =
                    body.signer ||
                    body.address ||
                    body.wallet ||
                    body.facilitator ||
                    (body.signers &&
                    body.signers["eip155:42793"] &&
                    Array.isArray(body.signers["eip155:42793"]) &&
                    body.signers["eip155:42793"][0]);
                if (signerAddress) {
                    log(`FACILITATOR SIGNER: ${signerAddress}`, "info");
                }
            }
            await loadTokenData();
        } catch (err) {
            log(`FACILITATOR CHECK FAILED: ${err.message}`, "error");
            if (err.message.includes("Failed to fetch")) {
                log("HINT: Check CORS or Mixed Content (HTTPS vs HTTP)", "info");
                log("HINT: Ensure Facilitator is running and accessible", "info");
            }
        }
    }

    function getStoreUrl() {
        return normalizeEndpointUrl(ui.storeInput.value, "");
    }

    function clearPaymentState() {
        cachedRequirements = null;
        ui.amount.innerText = "--";
        ui.payTo.innerText = "--";
        ui.payBtn.disabled = true;
        ui.payBtn.innerText = "4. SIGN & PAY";
    }

    function getStoreBaseUrl() {
        const storeUrl = getStoreUrl();
        if (!storeUrl) {
            return null;
        }
        try {
            const parsed = new URL(storeUrl);
            return `${parsed.protocol}//${parsed.host}`;
        } catch (err) {
            return null;
        }
    }

    function normalizeCatalogItemUrl(baseUrl, item) {
        if (!item || typeof item !== "object") {
            return null;
        }
        const raw = (item.url || item.path || "").toString().trim();
        if (!raw) {
            return null;
        }
        if (raw.startsWith("http://") || raw.startsWith("https://")) {
            return normalizeEndpointUrl(raw, "");
        }
        const normalizedPath = raw.startsWith("/") ? raw : `/${raw}`;
        return normalizeEndpointUrl(`${baseUrl}${normalizedPath}`, "");
    }

    function renderCatalog(items, currentStoreUrl) {
        catalogItems = Array.isArray(items) ? items : [];
        ui.catalogSelect.innerHTML = "";
        if (catalogItems.length === 0) {
            ui.catalogRow.classList.add("hidden");
            return;
        }

        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.innerText = "Select catalog item";
        ui.catalogSelect.appendChild(placeholder);

        let selectedValue = "";
        const current = (currentStoreUrl || "").toLowerCase();

        catalogItems.forEach((item) => {
            const option = document.createElement("option");
            option.value = item.url;
            const amount = item.payment && item.payment.amount ? item.payment.amount : "--";
            const id = item.id || "item";
            const name = item.name || item.description || item.path || item.url;
            option.innerText = `${id}: ${name} (${amount})`;
            ui.catalogSelect.appendChild(option);
            if (item.url && item.url.toLowerCase() === current) {
                selectedValue = item.url;
            }
        });

        if (!selectedValue && catalogItems[0] && catalogItems[0].url) {
            selectedValue = catalogItems[0].url;
        }

        if (selectedValue) {
            ui.catalogSelect.value = selectedValue;
            if (!currentStoreUrl || currentStoreUrl.toLowerCase() !== selectedValue.toLowerCase()) {
                ui.storeInput.value = selectedValue;
            }
        } else {
            ui.catalogSelect.value = "";
        }
        ui.catalogRow.classList.remove("hidden");
    }

    async function refreshCatalog() {
        const baseUrl = getStoreBaseUrl();
        if (!baseUrl) {
            ui.catalogRow.classList.add("hidden");
            catalogItems = [];
            return;
        }

        const catalogUrl = `${baseUrl}/api/catalog`;
        try {
            const resp = await fetch(catalogUrl, { cache: "no-store" });
            if (!resp.ok) {
                ui.catalogRow.classList.add("hidden");
                catalogItems = [];
                log(`CATALOG UNAVAILABLE (${resp.status}); USING DIRECT STORE URL`, "info");
                return;
            }

            const body = await resp.json();
            const products = Array.isArray(body.products) ? body.products : [];
            const normalizedItems = products
                .map((item) => {
                    const normalizedUrl = normalizeCatalogItemUrl(baseUrl, item);
                    if (!normalizedUrl) {
                        return null;
                    }
                    return {
                        id: item.id || "",
                        name: item.name || "",
                        description: item.description || "",
                        payment: item.payment || {},
                        url: normalizedUrl,
                    };
                })
                .filter(Boolean);

            if (normalizedItems.length === 0) {
                ui.catalogRow.classList.add("hidden");
                catalogItems = [];
                log("CATALOG HAS NO USABLE PRODUCTS; USING DIRECT STORE URL", "info");
                return;
            }

            renderCatalog(normalizedItems, getStoreUrl());
            log(`CATALOG LOADED (${normalizedItems.length} ITEM${normalizedItems.length > 1 ? "S" : ""})`, "success");
        } catch (err) {
            ui.catalogRow.classList.add("hidden");
            catalogItems = [];
            log(`CATALOG LOOKUP FAILED: ${err.message}`, "error");
        }
    }

    function onCatalogSelectionChanged() {
        const selectedUrl = ui.catalogSelect.value;
        if (!selectedUrl) {
            return;
        }
        ui.storeInput.value = selectedUrl;
        clearPaymentState();
        log(`CATALOG ITEM SELECTED: ${selectedUrl}`, "info");
    }

    async function onStoreUrlChanged() {
        clearPaymentState();
        await refreshCatalog();
    }

    function toBase64(text) {
        const data = new TextEncoder().encode(text);
        let binary = "";
        data.forEach((byte) => {
            binary += String.fromCharCode(byte);
        });
        return btoa(binary);
    }

    function fromBase64(text) {
        const binary = atob(text);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i += 1) {
            bytes[i] = binary.charCodeAt(i);
        }
        return new TextDecoder().decode(bytes);
    }

    let cachedRequirements = null;

    function formatExpiry(seconds) {
        if (!seconds || seconds === 0) {
            return "--";
        }
        const date = new Date(seconds * 1000);
        return date.toISOString().replace("T", " ").replace("Z", " UTC");
    }

    function getPermit2Token() {
        if (cachedRequirements && cachedRequirements.accepts && cachedRequirements.accepts[0]) {
            const asset = cachedRequirements.accepts[0].asset || "";
            // In x402 v2, `asset` is the raw token address.
            if (asset && asset.startsWith("0x") && asset.length === 42) {
                return asset;
            }
        }
        return BBT_ADDRESS;
    }

    function getSpenderForPermit2() {
        const raw = ui.spenderInput.value.trim() || DEFAULT_X402_EXACT_PERMIT2_PROXY_ADDRESS;
        try {
            return ethers.getAddress(raw);
        } catch (err) {
            return null;
        }
    }

    function getRequiredAmount() {
        if (!cachedRequirements || !cachedRequirements.accepts || !cachedRequirements.accepts[0]) {
            return null;
        }
        const accept = cachedRequirements.accepts[0];
        const raw = accept.amount || accept.maxAmountRequired;
        if (!raw) {
            return null;
        }
        try {
            return BigInt(raw.toString());
        } catch (err) {
            return null;
        }
    }

    function _trimFormattedAmount(value) {
        if (!value.includes(".")) {
            return value;
        }
        const trimmed = value.replace(/0+$/, "").replace(/\.$/, "");
        return trimmed || "0";
    }

    function getPaymentDisplay(accept) {
        const raw = accept && (accept.amount || accept.maxAmountRequired);
        const symbol = (accept && accept.extra && accept.extra.name) || "TOKEN";
        if (!raw) {
            return { amountText: "--", symbolText: symbol, buttonText: "4. SIGN & PAY" };
        }

        let amountText = raw.toString();
        try {
            const decimalsRaw =
                accept &&
                accept.extra &&
                (accept.extra.decimals ?? accept.extra.assetDecimals ?? accept.extra.tokenDecimals);
            const decimals = Number.isFinite(Number(decimalsRaw)) ? Number(decimalsRaw) : 18;
            amountText = _trimFormattedAmount(ethers.formatUnits(BigInt(raw.toString()), decimals));
        } catch (err) {
            amountText = raw.toString();
        }

        return {
            amountText,
            symbolText: symbol,
            buttonText: `4. SIGN & PAY ${amountText} ${symbol}`,
        };
    }

    function updateApproveButton(erc20Allowance) {
        const required = getRequiredAmount();
        if (!required || required <= 0n) {
            ui.approveBtn.disabled = true;
            ui.approveBtn.innerText = "GET PAYMENT FIRST";
            return;
        }

        const sufficient = erc20Allowance >= required;
        if (sufficient) {
            ui.approveBtn.disabled = true;
            ui.approveBtn.innerText = "APPROVED";
            return;
        }

        ui.approveBtn.disabled = false;
        ui.approveBtn.innerText = erc20Allowance > 0n ? "SET EXACT APPROVAL" : "APPROVE EXACT AMOUNT";
    }

    async function fetchPaymentRequirements() {
        const url = getStoreUrl();
        if (!url) {
            log("VALID STORE URL REQUIRED (HTTPS OR LOCALHOST HTTP)", "error");
            return;
        }
        clearPaymentState();

        try {
            log(`REQUESTING PAYMENT REQUIREMENTS: ${url}`, "info");
            const resp = await fetch(url);
            if (resp.status !== 402) {
                log(`EXPECTED 402, GOT ${resp.status}`, "error");
                return;
            }

            const header = resp.headers.get("payment-required") || resp.headers.get("Payment-Required");
            if (!header) {
                log("MISSING Payment-Required HEADER", "error");
                return;
            }

            const decoded = JSON.parse(fromBase64(header));
            cachedRequirements = decoded;

            const accept = decoded.accepts && decoded.accepts[0];
            if (!accept) {
                log("NO PAYMENT OPTIONS FOUND", "error");
                return;
            }

            const assetTransferMethod = accept.extra && accept.extra.assetTransferMethod;
            if (assetTransferMethod && assetTransferMethod !== "permit2") {
                log(`UNSUPPORTED assetTransferMethod: ${assetTransferMethod} (expected 'permit2')`, "error");
                ui.payBtn.disabled = true;
                return;
            }

            const payTo = accept.payTo;
            const display = getPaymentDisplay(accept);

            ui.amount.innerText = display.amountText;
            ui.payTo.innerText = payTo || "--";
            ui.payBtn.disabled = false;
            ui.payBtn.innerText = display.buttonText;

            if (signer) {
                await loadTokenData();
            }

            log("PAYMENT REQUIREMENTS LOADED", "success");
        } catch (err) {
            log(`FAILED TO GET REQUIREMENTS: ${err.message}`, "error");
        }
    }

    async function signAndPay() {
        if (!cachedRequirements) {
            log("GET PAYMENT REQUIREMENTS FIRST", "error");
            return;
        }
        const ready = await ensureWalletConnected();
        if (!ready) {
            log("WALLET NOT CONNECTED", "error");
            return;
        }

        const accept = cachedRequirements.accepts[0];
        const assetTransferMethod = accept.extra && accept.extra.assetTransferMethod;
        if (assetTransferMethod && assetTransferMethod !== "permit2") {
            log(`UNSUPPORTED assetTransferMethod: ${assetTransferMethod} (expected 'permit2')`, "error");
            return;
        }
        const tokenAddress = accept.asset;
        const payTo = accept.payTo;
        const amountRaw = accept.amount || accept.maxAmountRequired;
        const amount = BigInt(amountRaw);
        const acceptedRequirement = JSON.parse(JSON.stringify(accept));

        const spender = getSpenderForPermit2();
        if (!spender) {
            log("VALID SPENDER REQUIRED. CLICK CHECK /HEALTH OR ENTER A VALID X402 PROXY ADDRESS.", "error");
            return;
        }

        try {
            const decimals = await bbtContract.decimals();
            const erc20Allowance = await bbtContract.allowance(userAddress, PERMIT2_ADDRESS);
            if (erc20Allowance < amount) {
                log("ALLOWANCE TOO LOW. APPROVE PERMIT2 FIRST.", "error");
                return;
            }

            const domain = {
                name: "Permit2",
                chainId: ETHERLINK_CHAIN_ID,
                verifyingContract: PERMIT2_ADDRESS
            };

            let payload;
            // Coinbase x402 flow in this branch uses facilitator gas only.
            const now = Math.floor(Date.now() / 1000);
            const maxTimeoutSecondsRaw = accept.maxTimeoutSeconds;
            const maxTimeoutSeconds = Number.isFinite(Number(maxTimeoutSecondsRaw))
                ? Number(maxTimeoutSecondsRaw)
                : 60;
            if (maxTimeoutSeconds <= 0) {
                log(`INVALID maxTimeoutSeconds: ${maxTimeoutSecondsRaw}`, "error");
                return;
            }
            const deadline = BigInt(now + maxTimeoutSeconds);
            const validAfter = BigInt(now);
            const nonce = BigInt(ethers.hexlify(ethers.randomBytes(32)));

            const types = {
                PermitWitnessTransferFrom: [
                    { name: "permitted", type: "TokenPermissions" },
                    { name: "spender", type: "address" },
                    { name: "nonce", type: "uint256" },
                    { name: "deadline", type: "uint256" },
                    { name: "witness", type: "Witness" }
                ],
                TokenPermissions: [
                    { name: "token", type: "address" },
                    { name: "amount", type: "uint256" }
                ],
                Witness: [
                    { name: "to", type: "address" },
                    { name: "validAfter", type: "uint256" },
                    { name: "extra", type: "bytes" }
                ]
            };

            const value = {
                permitted: {
                    token: tokenAddress,
                    amount
                },
                spender,
                nonce,
                deadline,
                witness: {
                    to: payTo,
                    validAfter,
                    extra: "0x"
                }
            };

            log("SIGNING PERMIT2 (WITNESS)...", "info");
            const signature = await signer.signTypedData(domain, types, value);

            payload = {
                x402Version: 2,
                scheme: "exact",
                network: "eip155:42793",
                accepted: acceptedRequirement,
                payload: {
                    signature,
                    permit2Authorization: {
                        from: userAddress,
                        permitted: { token: tokenAddress, amount: amount.toString() },
                        spender,
                        nonce: nonce.toString(),
                        deadline: deadline.toString(),
                        witness: {
                            to: payTo,
                            validAfter: validAfter.toString(),
                            extra: "0x"
                        }
                    }
                }
            };

            const header = toBase64(JSON.stringify(payload));

            log("PERMIT2 SIGNATURE CREATED", "success");
            log(`PAYLOAD READY (base64 length=${header.length})`, "info");

            const headers = {
                "Payment-Signature": header,
                "X-GAS-PAYER": gasPayerMode
            };
            const storeUrl = getStoreUrl();
            if (!storeUrl) {
                log("VALID STORE URL REQUIRED (HTTPS OR LOCALHOST HTTP)", "error");
                return;
            }

            log("SENDING Payment-Signature...", "info");
            const resp = await fetch(storeUrl, {
                headers
            });

            const body = await resp.text();
            if (!resp.ok) {
                log(`PAYMENT FAILED: HTTP ${resp.status}`, "error");
                log(`RESPONSE: ${body}`, "error");
                return;
            }

            log("PAYMENT SENT. RESPONSE:", "success");
            log(body, "success");

            ui.amount.innerText = ethers.formatUnits(amount, decimals);
        } catch (err) {
            log(`SIGN/PAY FAILED: ${err.message}`, "error");
        }
    }

    // Start
    window.addEventListener('DOMContentLoaded', init);

