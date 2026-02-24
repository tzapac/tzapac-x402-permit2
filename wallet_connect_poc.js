// --- CONSTANTS ---
const BBT_ADDRESS = "0x7EfE4bdd11237610bcFca478937658bE39F8dfd6";
const PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3";
const DEFAULT_X402_EXACT_PERMIT2_PROXY_ADDRESS = "0xB6FD384A0626BfeF85f3dBaf5223Dd964684B09E";
const ETHERLINK_CHAIN_ID = 42793;
const ETHERLINK_CHAIN_ID_HEX = "0xA739";
const RPC_URL = "https://node.mainnet.etherlink.com";
const DISCLAIMER_ACK_STORAGE_KEY = "tez402_disclaimer_ack_at";
const DISCLAIMER_ACK_TTL_MS = 24 * 60 * 60 * 1000;
const ROLE_STORAGE_KEY = "tez402_role";
const IS_LOCAL_PAGE = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
const ANALYTICS_ENABLED = !IS_LOCAL_PAGE;
const DEFAULT_FACILITATOR_URL = IS_LOCAL_PAGE ? "http://localhost:9090" : "https://exp-faci.bubbletez.com";
const DEFAULT_STORE_URL = IS_LOCAL_PAGE ? "http://localhost:9091/api/weather" : "https://tez402.bubbletez.com/api/weather";
const LEGACY_STORE_URL = "https://exp-store.bubbletez.com/api/weather";
const CUSTOM_TIERS = {
    tier_0_01: "0.01",
    tier_0_1: "0.1",
    tier_1_0: "1.0"
};
const CUSTOM_SIGNATURE_WINDOW_SECONDS = 5 * 60;
const GA_MEASUREMENT_ID = "G-S1FE79SC2W";

function initAnalytics() {
    window.dataLayer = window.dataLayer || [];
    window.gtag = function gtag() {
        window.dataLayer.push(arguments);
    };
    window.gtag("js", new Date());
    window.gtag("config", GA_MEASUREMENT_ID, { anonymize_ip: true });
}

function sanitizeAnalyticsParams(params) {
    const safe = {};
    if (!params || typeof params !== "object") {
        return safe;
    }
    Object.entries(params).forEach(([key, value]) => {
        if (typeof value === "boolean" || typeof value === "number") {
            safe[key] = value;
            return;
        }
        if (typeof value !== "string") {
            return;
        }
        const trimmed = value.trim();
        if (!trimmed) {
            return;
        }
        if (/^0x[a-fA-F0-9]{40}$/.test(trimmed)) {
            return;
        }
        safe[key] = trimmed.slice(0, 80);
    });
    return safe;
}

function trackEvent(eventName, params = {}) {
    if (!ANALYTICS_ENABLED || typeof window.gtag !== "function") {
        return;
    }
    if (typeof eventName !== "string" || !eventName.startsWith("tez402_")) {
        return;
    }
    window.gtag("event", eventName, sanitizeAnalyticsParams(params));
}

initAnalytics();
const ETHERS_CDN_URLS = [
    "https://cdn.jsdelivr.net/npm/ethers@6.13.4/dist/ethers.umd.min.js",
    "https://unpkg.com/ethers@6.13.4/dist/ethers.umd.min.js"
];

const ROLE_DESCRIPTIONS = {
    client: "You are viewing client-first guidance. Start with Demo, then implement 402 parsing and Payment-Signature retry.",
    store: "You are viewing store-first guidance. Focus on 402 requirement generation and facilitator settlement gating.",
    facilitator: "You are viewing facilitator-first guidance. Focus on hosted settlement reliability, allowlist policy, and signer operations."
};

// --- STATE ---
let provider;
let signer;
let activeTokenContract;
let userAddress;
let gasPayerMode = "facilitator";
let tokenDetailsOpen = false;
let facilitatorOnline = null;
let facilitatorPollTimer = null;
let catalogItems = [];
let appInitialized = false;
let currentRole = "client";
let currentActiveTab = "";
let cachedRequirements = null;
let activeTokenAddress = BBT_ADDRESS;
let activeTokenSymbol = "BBT";
let activeTokenDecimals = 18;

// --- ABI ---
const ERC20_ABI = [
    "function decimals() view returns (uint8)",
    "function balanceOf(address) view returns (uint256)",
    "function allowance(address, address) view returns (uint256)",
    "function approve(address, uint256) returns (bool)"
];

// --- UI ELEMENTS ---
const ui = {
    statusDot: document.getElementById("status-dot"),
    statusText: document.getElementById("status-text"),

    connectBtn: document.getElementById("connect-btn"),
    approveBtn: document.getElementById("approve-btn"),
    healthBtn: document.getElementById("health-btn"),
    requirementsBtn: document.getElementById("requirements-btn"),
    payBtn: document.getElementById("pay-btn"),

    facilitatorInput: document.getElementById("facilitator-input"),
    spenderInput: document.getElementById("spender-input"),
    storeInput: document.getElementById("store-input"),
    catalogRow: document.getElementById("catalog-row"),
    catalogSelect: document.getElementById("catalog-select"),
    customTokenInput: document.getElementById("custom-token-input"),
    customTierSelect: document.getElementById("custom-tier-select"),
    customCreateBtn: document.getElementById("custom-create-btn"),
    customCreateStatus: document.getElementById("custom-create-status"),

    network: document.getElementById("network-display"),
    account: document.getElementById("account-display"),
    balance: document.getElementById("balance-display"),
    allowance: document.getElementById("allowance-display"),
    permit2AllowanceRow: document.getElementById("permit2-allowance-row"),
    permit2Allowance: document.getElementById("permit2-allowance-display"),
    permit2Expiration: document.getElementById("permit2-expiration-display"),
    permit2Nonce: document.getElementById("permit2-nonce-display"),
    amount: document.getElementById("amount-display"),
    payTo: document.getElementById("payto-display"),
    tokenSymbol: document.getElementById("token-symbol-display"),
    tokenAddress: document.getElementById("token-address-display"),
    tokenDecimals: document.getElementById("token-decimals-display"),

    tokenSection: document.getElementById("token-section"),
    tokenToggleBtn: document.getElementById("token-toggle-btn"),
    gasFacilitatorBtn: document.getElementById("gas-facilitator-btn"),

    disclaimerOverlay: document.getElementById("disclaimer-overlay"),
    disclaimerOkBtn: document.getElementById("disclaimer-ok-btn"),
    termsBackBtn: document.getElementById("terms-back-btn"),
    tosBackBtn: document.getElementById("tos-back-btn"),

    goDemoBtn: document.getElementById("go-demo-btn"),
    goIntegrationBtn: document.getElementById("go-integration-btn"),
    goSetupBtn: document.getElementById("go-setup-btn"),

    roleClientBtn: document.getElementById("role-client-btn"),
    roleStoreBtn: document.getElementById("role-store-btn"),
    roleFacilitatorBtn: document.getElementById("role-facilitator-btn"),
    roleSummary: document.getElementById("role-summary"),

    stepStatus1: document.getElementById("step-status-1"),
    stepStatus2: document.getElementById("step-status-2"),
    stepStatus3: document.getElementById("step-status-3"),
    stepStatus4: document.getElementById("step-status-4"),
    stepStatus5: document.getElementById("step-status-5"),

    healthResponse: document.getElementById("health-response"),
    requirementsResponse: document.getElementById("requirements-response"),
    settleResponse: document.getElementById("settle-response"),

    console: document.getElementById("console-output")
};

const tabButtons = Array.from(document.querySelectorAll(".tab-button"));
const tabPanels = Array.from(document.querySelectorAll(".tab-panel"));
const roleButtons = Array.from(document.querySelectorAll(".role-button"));
const copyButtons = Array.from(document.querySelectorAll(".copy-btn"));

// --- LOGGING ---
function log(msg, type = "info") {
    if (!ui.console) {
        return;
    }
    const div = document.createElement("div");
    div.className = `log-entry log-${type}`;
    div.innerText = `> ${msg}`;
    ui.console.appendChild(div);
    ui.console.scrollTop = ui.console.scrollHeight;
}

function setResponsePreview(element, data) {
    if (!element) {
        return;
    }
    if (typeof data === "string") {
        element.textContent = data;
        return;
    }
    try {
        element.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
        element.textContent = String(data);
    }
}

function setCustomCreateStatus(message, type = "info") {
    if (!ui.customCreateStatus) {
        return;
    }
    ui.customCreateStatus.classList.remove("success", "error");
    if (type === "success" || type === "error") {
        ui.customCreateStatus.classList.add(type);
    }
    ui.customCreateStatus.textContent = message;
}

function normalizeAddress(value) {
    try {
        return ethers.getAddress((value || "").trim());
    } catch (err) {
        return null;
    }
}

function getCreateNonce() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
        return window.crypto.randomUUID();
    }
    return ethers.hexlify(ethers.randomBytes(16));
}

function getCanonicalCreateMessage(data) {
    return [
        "tez402 Custom Product Creation",
        `chainId:${data.chainId}`,
        `creator:${data.creator}`,
        `token:${data.token}`,
        `tierId:${data.tierId}`,
        `nonce:${data.nonce}`,
        `issuedAt:${data.issuedAt}`,
        `expiresAt:${data.expiresAt}`
    ].join("\n");
}

function setStepStatus(step, state, label) {
    const map = {
        1: ui.stepStatus1,
        2: ui.stepStatus2,
        3: ui.stepStatus3,
        4: ui.stepStatus4,
        5: ui.stepStatus5
    };
    const el = map[step];
    if (!el) {
        return;
    }
    el.classList.remove("pending", "active", "success", "error");
    el.classList.add(state);
    el.textContent = label;
}

function resetDemoStepStatuses() {
    setStepStatus(1, "pending", "Not started");
    setStepStatus(2, "pending", "Not started");
    setStepStatus(3, "pending", "Not started");
    setStepStatus(4, "pending", "Not started");
    setStepStatus(5, "pending", "Not started");
}

function normalizeRole(role) {
    if (["client", "store", "facilitator"].includes(role)) {
        return role;
    }
    return "client";
}

function setRole(role) {
    currentRole = normalizeRole(role);
    if (window.localStorage) {
        localStorage.setItem(ROLE_STORAGE_KEY, currentRole);
    }

    roleButtons.forEach((button) => {
        button.classList.toggle("active", button.dataset.role === currentRole);
    });

    document.querySelectorAll("[data-role-panel]").forEach((panel) => {
        panel.classList.toggle("hidden", panel.dataset.rolePanel !== currentRole);
    });

    document.querySelectorAll("[data-role-checklist]").forEach((panel) => {
        panel.classList.toggle("hidden", panel.dataset.roleChecklist !== currentRole);
    });

    if (ui.roleSummary) {
        ui.roleSummary.textContent = ROLE_DESCRIPTIONS[currentRole];
    }
}

function initialRoleFromContext() {
    try {
        const query = new URLSearchParams(window.location.search);
        const rawRole = (query.get("role") || "").toLowerCase();
        if (rawRole) {
            return normalizeRole(rawRole);
        }
    } catch (err) {
        // ignore query parsing issues
    }

    if (!window.localStorage) {
        return "client";
    }

    const stored = localStorage.getItem(ROLE_STORAGE_KEY);
    return normalizeRole((stored || "client").toLowerCase());
}

function hasRecentDisclaimerAcknowledgement() {
    if (!window.localStorage) {
        return false;
    }

    const raw = localStorage.getItem(DISCLAIMER_ACK_STORAGE_KEY);
    if (!raw) {
        return false;
    }

    const acknowledgedAt = Number(raw);
    if (!Number.isFinite(acknowledgedAt)) {
        localStorage.removeItem(DISCLAIMER_ACK_STORAGE_KEY);
        return false;
    }

    return Date.now() - acknowledgedAt < DISCLAIMER_ACK_TTL_MS;
}

function setDisclaimerAcknowledged() {
    if (!window.localStorage) {
        return;
    }

    localStorage.setItem(DISCLAIMER_ACK_STORAGE_KEY, String(Date.now()));
}

function bindCopyButtons() {
    copyButtons.forEach((button) => {
        button.addEventListener("click", async () => {
            const targetId = button.dataset.copyTarget;
            const value = targetId
                ? (document.getElementById(targetId)?.innerText || "")
                : (button.dataset.copyValue || "");

            if (!value) {
                log("COPY FAILED: NO VALUE", "error");
                return;
            }

            try {
                await navigator.clipboard.writeText(value.trim());
                log("COPIED TO CLIPBOARD", "success");
                trackEvent("tez402_copy_address", { target: targetId || "unknown" });
            } catch (err) {
                const temp = document.createElement("textarea");
                temp.value = value.trim();
                document.body.appendChild(temp);
                temp.select();
                document.execCommand("copy");
                document.body.removeChild(temp);
                log("COPIED TO CLIPBOARD", "success");
                trackEvent("tez402_copy_address", { target: targetId || "unknown" });
            }
        });
    });
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
    if (appInitialized) {
        return;
    }
    appInitialized = true;
    trackEvent("tez402_page_loaded", { host: window.location.hostname });

    resetDemoStepStatuses();
    setResponsePreview(ui.healthResponse, "Awaiting response...");
    setResponsePreview(ui.requirementsResponse, "Awaiting response...");
    setResponsePreview(ui.settleResponse, "Awaiting response...");

    if (ui.facilitatorInput && !ui.facilitatorInput.value) {
        ui.facilitatorInput.value = DEFAULT_FACILITATOR_URL;
    }
    if (ui.facilitatorInput) {
        ui.facilitatorInput.placeholder = `Current endpoint: ${DEFAULT_FACILITATOR_URL}`;
    }
    if (ui.storeInput && !ui.storeInput.value) {
        ui.storeInput.value = DEFAULT_STORE_URL;
    }
    if (ui.storeInput) {
        ui.storeInput.placeholder = `Legacy endpoint: ${LEGACY_STORE_URL}`;
    }
    if (ui.spenderInput && !ui.spenderInput.value) {
        ui.spenderInput.value = DEFAULT_X402_EXACT_PERMIT2_PROXY_ADDRESS;
    }

    bindCopyButtons();

    if (ui.connectBtn) ui.connectBtn.addEventListener("click", connectWallet);
    if (ui.approveBtn) ui.approveBtn.addEventListener("click", approvePermit2);
    if (ui.healthBtn) ui.healthBtn.addEventListener("click", checkFacilitatorHealth);
    if (ui.requirementsBtn) ui.requirementsBtn.addEventListener("click", fetchPaymentRequirements);
    if (ui.payBtn) ui.payBtn.addEventListener("click", signAndPay);
    if (ui.customCreateBtn) ui.customCreateBtn.addEventListener("click", createCustomTokenProduct);
    if (ui.tokenToggleBtn) ui.tokenToggleBtn.addEventListener("click", toggleTokenDetails);
    if (ui.gasFacilitatorBtn) ui.gasFacilitatorBtn.addEventListener("click", () => setGasPayerMode("facilitator"));
    if (ui.catalogSelect) ui.catalogSelect.addEventListener("change", onCatalogSelectionChanged);
    if (ui.storeInput) {
        ui.storeInput.addEventListener("change", onStoreUrlChanged);
        ui.storeInput.addEventListener("blur", onStoreUrlChanged);
    }

    if (ui.goDemoBtn) ui.goDemoBtn.addEventListener("click", () => setActiveTab("demo"));
    if (ui.goIntegrationBtn) ui.goIntegrationBtn.addEventListener("click", () => setActiveTab("integration"));
    if (ui.goSetupBtn) ui.goSetupBtn.addEventListener("click", () => setActiveTab("setup"));

    roleButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const selectedRole = normalizeRole(button.dataset.role);
            setRole(selectedRole);
            trackEvent("tez402_role_select", { role: selectedRole });
        });
    });

    const hideDisclaimerOverlay = (event) => {
        if (event && event.preventDefault) {
            event.preventDefault();
        }
        if (!ui.disclaimerOverlay) {
            return;
        }

        setDisclaimerAcknowledged();
        trackEvent("tez402_disclaimer_ack", { source: "modal" });

        if (document.activeElement === ui.disclaimerOkBtn) {
            ui.disclaimerOkBtn.blur();
        }

        ui.disclaimerOverlay.style.display = "none";
        ui.disclaimerOverlay.classList.add("hidden");
        document.body.style.overflow = "";

        const focusTarget = tabButtons.find((button) => button.dataset.tab === "overview") || tabButtons[0];
        if (focusTarget) {
            focusTarget.focus({ preventScroll: true });
        }
    };

    const showDisclaimerOverlay = () => {
        if (!ui.disclaimerOverlay) {
            return;
        }

        ui.disclaimerOverlay.style.display = "flex";
        ui.disclaimerOverlay.classList.remove("hidden");
        document.body.style.overflow = "hidden";
        if (ui.disclaimerOkBtn) {
            ui.disclaimerOkBtn.focus({ preventScroll: true });
        }
    };

    if (ui.disclaimerOkBtn) {
        ui.disclaimerOkBtn.addEventListener("click", hideDisclaimerOverlay);
    }

    tabButtons.forEach((button) => {
        button.addEventListener("click", () => setActiveTab(button.dataset.tab));
    });

    setActiveTab("overview");
    if (ui.termsBackBtn) {
        ui.termsBackBtn.addEventListener("click", () => setActiveTab("demo"));
    }

    if (ui.tosBackBtn) {
        ui.tosBackBtn.addEventListener("click", () => setActiveTab("demo"));
    }

    setRole(initialRoleFromContext());
    setGasPayerMode("facilitator");
    updateTokenToggle();
    updateTokenDetailsDisplay();
    setCustomCreateStatus("No custom product created in this session.");
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

    if (!hasRecentDisclaimerAcknowledgement()) {
        showDisclaimerOverlay();
    } else {
        hideDisclaimerOverlay();
    }

    const accounts = await window.ethereum.request({ method: "eth_accounts" });
    if (accounts.length > 0) {
        connectWallet();
    }

    window.ethereum.on("chainChanged", () => window.location.reload());
    window.ethereum.on("accountsChanged", () => window.location.reload());
}

function setActiveTab(tabName) {
    const normalized = tabPanels.some((panel) => panel.dataset.panel === tabName)
        ? tabName
        : "overview";
    tabButtons.forEach((button) => {
        button.classList.toggle("active", button.dataset.tab === normalized);
    });
    tabPanels.forEach((panel) => {
        panel.classList.toggle("hidden", panel.dataset.panel !== normalized);
    });
    if (currentActiveTab !== normalized) {
        currentActiveTab = normalized;
        trackEvent("tez402_tab_view", { tab_name: normalized });
    }
}

function setFacilitatorStatus(isOnline) {
    if (facilitatorOnline === isOnline) {
        return;
    }
    facilitatorOnline = isOnline;
    if (ui.statusDot) {
        ui.statusDot.classList.toggle("active", isOnline);
    }
    if (ui.statusText) {
        ui.statusText.innerText = isOnline ? "ONLINE" : "OFFLINE";
    }
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
    if (ui.facilitatorInput) {
        ui.facilitatorInput.addEventListener("change", pollFacilitatorSupported);
    }
}

// --- CONNECT WALLET ---
async function connectWallet() {
    try {
        setStepStatus(1, "active", "In progress");
        log("INITIALIZING CONNECTION...", "info");
        trackEvent("tez402_wallet_connect_click", { source: "button" });
        provider = new ethers.BrowserProvider(window.ethereum);

        await provider.send("eth_requestAccounts", []);
        signer = await provider.getSigner();
        userAddress = await signer.getAddress();

        log(`CONNECTED: ${userAddress.slice(0, 6)}...${userAddress.slice(-4)}`, "success");
        if (ui.account) {
            ui.account.innerText = userAddress;
        }

        if (ui.connectBtn) {
            ui.connectBtn.disabled = true;
            ui.connectBtn.innerText = "1. CONNECTED";
        }

        await reportWalletConnection();
        await checkNetwork();
        await refreshCatalog();
        setStepStatus(1, "success", "Complete");
        trackEvent("tez402_wallet_connect_success", { network_target: ETHERLINK_CHAIN_ID });
    } catch (err) {
        setStepStatus(1, "error", "Error");
        log(`CONNECTION FAILED: ${err.message}`, "error");
        trackEvent("tez402_wallet_connect_error", { reason: "connect_failed" });
    }
}

async function reportWalletConnection() {
    const facilitatorUrl = getFacilitatorUrl();
    if (!facilitatorUrl || !userAddress) {
        return;
    }

    const payload = {
        wallet: userAddress,
        reason: "wallet-connected",
        source: "wallet_connect_poc",
        metadata: {
            page: "wallet_connect_poc",
            connectedAt: new Date().toISOString(),
            storeUrl: getStoreUrl(),
            facilitatorUrl,
            userAgent: navigator.userAgent || ""
        }
    };

    try {
        const response = await fetch(`${facilitatorUrl}/compliance/connect`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });
        if (!response.ok) {
            log(`WALLET CONNECT AUDIT FAILED (${response.status})`, "error");
        }
    } catch (error) {
        log(`WALLET CONNECT AUDIT ERROR: ${error.message}`, "error");
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
    if (ui.approveBtn) ui.approveBtn.disabled = true;
    if (ui.payBtn) ui.payBtn.disabled = true;
    if (ui.connectBtn) ui.connectBtn.disabled = true;
}

function updateTokenToggle() {
    if (!ui.tokenToggleBtn) {
        return;
    }
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
        if (!activeTokenContract) {
            await loadTokenData();
        }
        if (ui.tokenSection) {
            ui.tokenSection.classList.remove("hidden");
        }
    } else if (ui.tokenSection) {
        ui.tokenSection.classList.add("hidden");
    }
    updateTokenToggle();
}

function setGasPayerMode(mode) {
    gasPayerMode = "facilitator";
    if (ui.gasFacilitatorBtn) {
        ui.gasFacilitatorBtn.classList.add("active");
    }
    if (mode !== "facilitator") {
        log("ONLY FACILITATOR GAS MODE IS ENABLED IN TEZ402-ALIGNED FLOW", "info");
    }
    log("GAS PAYER: FACILITATOR", "info");
}

// --- NETWORK ---
async function checkNetwork() {
    const network = await provider.getNetwork();
    const chainId = Number(network.chainId);

    if (chainId !== ETHERLINK_CHAIN_ID) {
        log(`WRONG NETWORK DETECTED (ID: ${chainId})`, "error");
        trackEvent("tez402_network_mismatch", { chain_id: chainId });
        if (ui.network) {
            ui.network.innerText = "WRONG NETWORK";
            ui.network.style.color = "var(--error-color)";
        }
        await switchNetwork();
    } else {
        if (ui.network) {
            ui.network.innerText = "ETHERLINK MAINNET";
            ui.network.style.color = "var(--accent-color)";
        }
        log("NETWORK VERIFIED: ETHERLINK", "success");
        trackEvent("tez402_network_verified", { chain_id: chainId });
        await loadTokenData();
    }
}

async function switchNetwork() {
    try {
        log("ATTEMPTING NETWORK SWITCH...", "info");
        trackEvent("tez402_network_switch_attempt", { target_chain_id: ETHERLINK_CHAIN_ID });
        await window.ethereum.request({
            method: "wallet_switchEthereumChain",
            params: [{ chainId: ETHERLINK_CHAIN_ID_HEX }]
        });
        trackEvent("tez402_network_switch_success", { method: "switch" });
        window.location.reload();
    } catch (switchError) {
        if (switchError.code === 4902) {
            log("NETWORK NOT FOUND. ADDING ETHERLINK...", "info");
            trackEvent("tez402_network_add_attempt", { target_chain_id: ETHERLINK_CHAIN_ID });
            try {
                await window.ethereum.request({
                    method: "wallet_addEthereumChain",
                    params: [
                        {
                            chainId: ETHERLINK_CHAIN_ID_HEX,
                            chainName: "Etherlink Mainnet",
                            rpcUrls: [RPC_URL],
                            nativeCurrency: {
                                name: "Tezos",
                                symbol: "XTZ",
                                decimals: 18
                            },
                            blockExplorerUrls: ["https://explorer.etherlink.com/"]
                        }
                    ]
                });
                trackEvent("tez402_network_add_success", { method: "add_chain" });
                window.location.reload();
            } catch (addError) {
                log(`FAILED TO ADD NETWORK: ${addError.message}`, "error");
                trackEvent("tez402_network_add_error", { reason: "add_failed" });
            }
        } else {
            log(`FAILED TO SWITCH NETWORK: ${switchError.message}`, "error");
            trackEvent("tez402_network_switch_error", { reason: "switch_failed" });
        }
    }
}

// --- TOKEN DATA ---
function getActivePaymentAccept() {
    return cachedRequirements && cachedRequirements.accepts ? cachedRequirements.accepts[0] : null;
}

function getActiveTokenSymbolFromAccept(accept) {
    if (accept && accept.extra && accept.extra.name) {
        return String(accept.extra.name);
    }
    if (getPermit2Token().toLowerCase() === BBT_ADDRESS.toLowerCase()) {
        return "BBT";
    }
    return "TOKEN";
}

function getActiveTokenDecimalsFromAccept(accept) {
    const decimalsRaw = accept && accept.extra
        ? (accept.extra.decimals ?? accept.extra.assetDecimals ?? accept.extra.tokenDecimals)
        : null;
    const decimals = Number(decimalsRaw);
    if (!Number.isFinite(decimals) || decimals < 0 || decimals > 255) {
        return 18;
    }
    return decimals;
}

function updateTokenDetailsDisplay() {
    if (ui.tokenSymbol) {
        ui.tokenSymbol.innerText = activeTokenSymbol || "TOKEN";
    }
    if (ui.tokenAddress) {
        ui.tokenAddress.innerText = activeTokenAddress || BBT_ADDRESS;
    }
    if (ui.tokenDecimals) {
        ui.tokenDecimals.innerText = String(activeTokenDecimals);
    }
}

async function loadTokenData() {
    try {
        if (!signer || !userAddress) {
            return;
        }
        const tokenAddress = getPermit2Token();
        const accept = getActivePaymentAccept();

        if (!activeTokenContract || activeTokenAddress.toLowerCase() !== tokenAddress.toLowerCase()) {
            activeTokenContract = new ethers.Contract(tokenAddress, ERC20_ABI, signer);
        }
        activeTokenAddress = tokenAddress;
        activeTokenSymbol = getActiveTokenSymbolFromAccept(accept);

        let decimals = getActiveTokenDecimalsFromAccept(accept);
        try {
            decimals = Number(await activeTokenContract.decimals());
        } catch (decimalsErr) {
            // Keep fallback from Payment-Required metadata.
        }
        if (!Number.isFinite(decimals) || decimals < 0 || decimals > 255) {
            decimals = 18;
        }
        activeTokenDecimals = decimals;
        updateTokenDetailsDisplay();

        const balance = await activeTokenContract.balanceOf(userAddress);
        const erc20Allowance = await activeTokenContract.allowance(userAddress, PERMIT2_ADDRESS);

        if (ui.balance) ui.balance.innerText = ethers.formatUnits(balance, decimals);
        if (ui.allowance) ui.allowance.innerText = ethers.formatUnits(erc20Allowance, decimals);

        const spender = getSpenderForPermit2();
        if (spender) {
            const permit2Abi = [
                "function allowance(address owner,address token,address spender) view returns (uint160 amount,uint48 expiration,uint48 nonce)"
            ];
            const permit2 = new ethers.Contract(PERMIT2_ADDRESS, permit2Abi, provider);
            const allowanceData = await permit2.allowance(userAddress, tokenAddress, spender);
            const permit2Amount = allowanceData[0];
            const permit2Expiration = allowanceData[1];
            const permit2Nonce = allowanceData[2];

            if (permit2Amount > 0n) {
                if (ui.permit2AllowanceRow) ui.permit2AllowanceRow.classList.remove("hidden");
                if (ui.permit2Allowance) ui.permit2Allowance.innerText = ethers.formatUnits(permit2Amount, decimals);
            } else {
                if (ui.permit2AllowanceRow) ui.permit2AllowanceRow.classList.add("hidden");
                if (ui.permit2Allowance) ui.permit2Allowance.innerText = "--";
            }
            if (ui.permit2Expiration) ui.permit2Expiration.innerText = formatExpiry(Number(permit2Expiration));
            if (ui.permit2Nonce) ui.permit2Nonce.innerText = permit2Nonce.toString();
        } else {
            if (ui.permit2AllowanceRow) ui.permit2AllowanceRow.classList.add("hidden");
            if (ui.permit2Allowance) ui.permit2Allowance.innerText = "--";
            if (ui.permit2Expiration) ui.permit2Expiration.innerText = "--";
            if (ui.permit2Nonce) ui.permit2Nonce.innerText = "--";
        }

        updateApproveButton(erc20Allowance);

        if (tokenDetailsOpen && ui.tokenSection) {
            ui.tokenSection.classList.remove("hidden");
        }
        if (ui.approveBtn) {
            ui.approveBtn.classList.remove("hidden");
        }

        if (erc20Allowance >= (getRequiredAmount() || 0n)) {
            setStepStatus(4, "success", "Ready/Complete");
        }

        log(`TOKEN DATA LOADED (${activeTokenSymbol} ${activeTokenAddress})`, "success");
    } catch (err) {
        log(`FAILED TO LOAD TOKEN DATA: ${err.message}`, "error");
    }
}

// --- APPROVE ---
async function approvePermit2() {
    const ready = await ensureWalletConnected();
    if (!ready) {
        trackEvent("tez402_approve_error", { stage: "wallet_not_ready" });
        return;
    }
    trackEvent("tez402_approve_click", { source: "step4" });
    if (!activeTokenContract) {
        await loadTokenData();
    }
    if (!activeTokenContract) return;

    try {
        setStepStatus(4, "active", "In progress");
        if (ui.approveBtn) {
            ui.approveBtn.disabled = true;
            ui.approveBtn.innerText = "SIGNING...";
        }
        log("INITIATING APPROVAL TRANSACTION...", "info");

        const requiredAmount = getRequiredAmount();
        if (!requiredAmount || requiredAmount <= 0n) {
            log("GET PAYMENT REQUIREMENTS FIRST TO APPROVE THE EXACT AMOUNT.", "error");
            if (ui.approveBtn) {
                ui.approveBtn.disabled = false;
                ui.approveBtn.innerText = "GET PAYMENT FIRST";
            }
            setStepStatus(4, "error", "Blocked");
            return;
        }

        const tx = await activeTokenContract.approve(PERMIT2_ADDRESS, requiredAmount);
        log(`TX SENT: ${tx.hash}`, "info");
        trackEvent("tez402_approve_tx_sent", { source: "step4" });
        if (ui.approveBtn) {
            ui.approveBtn.innerText = "PENDING...";
        }

        await tx.wait();

        log("APPROVAL CONFIRMED", "success");
        setStepStatus(4, "success", "Complete");
        trackEvent("tez402_approve_confirmed", { source: "step4" });

        await loadTokenData();
    } catch (err) {
        log(`APPROVAL FAILED: ${err.message}`, "error");
        setStepStatus(4, "error", "Error");
        trackEvent("tez402_approve_error", { stage: "transaction_failed" });
        if (ui.approveBtn) {
            ui.approveBtn.disabled = false;
            ui.approveBtn.innerText = "APPROVE PERMIT2";
        }
    }
}

// --- URL HELPERS ---
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
    return normalizeEndpointUrl(ui.facilitatorInput?.value || "", DEFAULT_FACILITATOR_URL);
}

function getStoreUrl() {
    return normalizeEndpointUrl(ui.storeInput?.value || "", "");
}

// --- FACILITATOR ---
async function checkFacilitatorHealth() {
    const base = getFacilitatorUrl();
    if (!base) {
        setFacilitatorStatus(false);
        setStepStatus(2, "error", "Invalid URL");
        log("INVALID FACILITATOR URL. USE HTTPS (OR HTTP FOR LOCALHOST).", "error");
        trackEvent("tez402_facilitator_health_error", { reason: "invalid_url" });
        return;
    }

    const url = `${base}/health`;
    try {
        setStepStatus(2, "active", "In progress");
        log(`CHECKING FACILITATOR: ${url}`, "info");
        trackEvent("tez402_facilitator_health_check", { endpoint: "health" });
        const resp = await fetch(url);
        const contentType = resp.headers.get("content-type") || "";
        const body = contentType.includes("application/json") ? await resp.json() : await resp.text();

        setResponsePreview(ui.healthResponse, body);

        if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
        }
        log("FACILITATOR HEALTHY", "success");
        setStepStatus(2, "success", "Complete");
        setFacilitatorStatus(true);
        trackEvent("tez402_facilitator_health_success", { status: resp.status });

        if (ui.spenderInput && !ui.spenderInput.value) {
            ui.spenderInput.value = DEFAULT_X402_EXACT_PERMIT2_PROXY_ADDRESS;
            log(`SPENDER DEFAULTED TO X402 PROXY: ${DEFAULT_X402_EXACT_PERMIT2_PROXY_ADDRESS}`, "success");
        }

        await loadTokenData();
    } catch (err) {
        setStepStatus(2, "error", "Error");
        log(`FACILITATOR CHECK FAILED: ${err.message}`, "error");
        trackEvent("tez402_facilitator_health_error", { reason: "request_failed" });
        if (err.message.includes("Failed to fetch")) {
            log("HINT: Check CORS or Mixed Content (HTTPS vs HTTP)", "info");
            log("HINT: Ensure Facilitator is running and accessible", "info");
        }
    }
}

async function createCustomTokenProduct() {
    const walletReady = await ensureWalletConnected();
    if (!walletReady) {
        setCustomCreateStatus("Connect wallet before creating a custom product.", "error");
        trackEvent("tez402_custom_product_create_error", { stage: "wallet_not_ready" });
        return;
    }

    const baseUrl = getStoreBaseUrl();
    if (!baseUrl) {
        setCustomCreateStatus("Valid Store API URL required before creating product.", "error");
        log("CUSTOM CREATE FAILED: INVALID STORE URL", "error");
        trackEvent("tez402_custom_product_create_error", { stage: "invalid_store_url" });
        return;
    }

    const tokenAddress = normalizeAddress(ui.customTokenInput?.value || "");
    if (!tokenAddress) {
        setCustomCreateStatus("Enter a valid ERC-20 token address.", "error");
        log("CUSTOM CREATE FAILED: INVALID TOKEN ADDRESS", "error");
        trackEvent("tez402_custom_product_create_error", { stage: "invalid_token" });
        return;
    }

    const tierId = (ui.customTierSelect?.value || "").trim();
    if (!CUSTOM_TIERS[tierId]) {
        setCustomCreateStatus("Choose a valid tier before creating product.", "error");
        log("CUSTOM CREATE FAILED: INVALID TIER", "error");
        trackEvent("tez402_custom_product_create_error", { stage: "invalid_tier" });
        return;
    }

    const creator = normalizeAddress(userAddress);
    if (!creator) {
        setCustomCreateStatus("Wallet address unavailable. Reconnect wallet and retry.", "error");
        return;
    }

    try {
        if (ui.customCreateBtn) {
            ui.customCreateBtn.disabled = true;
            ui.customCreateBtn.textContent = "CREATING...";
        }
        setCustomCreateStatus("Signing creation message...", "info");
        log(`SIGNING CUSTOM PRODUCT MESSAGE (${tierId})`, "info");
        trackEvent("tez402_custom_product_create_attempt", { tier_id: tierId });

        const now = Math.floor(Date.now() / 1000);
        const payload = {
            creator,
            token: tokenAddress,
            tierId,
            nonce: getCreateNonce(),
            issuedAt: now,
            expiresAt: now + CUSTOM_SIGNATURE_WINDOW_SECONDS,
            chainId: ETHERLINK_CHAIN_ID
        };
        const canonicalMessage = getCanonicalCreateMessage(payload);
        const signature = await signer.signMessage(canonicalMessage);

        const createBody = { ...payload, signature };
        const createUrl = `${baseUrl}/api/catalog/custom-token`;
        setCustomCreateStatus("Submitting create request...", "info");
        log(`POST ${createUrl}`, "info");

        const resp = await fetch(createUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(createBody)
        });

        const contentType = resp.headers.get("content-type") || "";
        const responseBody = contentType.includes("application/json") ? await resp.json() : await resp.text();
        if (!resp.ok) {
            const message = typeof responseBody === "string"
                ? responseBody
                : (responseBody.error || responseBody.message || JSON.stringify(responseBody));
            setCustomCreateStatus(`Create failed (${resp.status}): ${message}`, "error");
            log(`CUSTOM CREATE FAILED (${resp.status})`, "error");
            trackEvent("tez402_custom_product_create_error", { stage: "http_error", status: resp.status });
            return;
        }

        const product = responseBody && responseBody.product ? responseBody.product : null;
        const createdUrl = product ? normalizeCatalogItemUrl(baseUrl, product) : null;
        clearPaymentState();
        await refreshCatalog(createdUrl || undefined);

        if (createdUrl && ui.storeInput) {
            ui.storeInput.value = createdUrl;
        }

        const symbol = product && product.payment && product.payment.extra
            ? (product.payment.extra.name || "TOKEN")
            : "TOKEN";
        setCustomCreateStatus(
            `Created ${product?.id || "product"} (${CUSTOM_TIERS[tierId]} ${symbol}). Payment cache cleared. Click 3. GET PAYMENT.`,
            "success"
        );
        log(`CUSTOM PRODUCT CREATED: ${product?.id || "unknown-id"}`, "success");
        trackEvent("tez402_custom_product_create_success", { tier_id: tierId });
    } catch (err) {
        setCustomCreateStatus(`Create failed: ${err.message}`, "error");
        log(`CUSTOM CREATE ERROR: ${err.message}`, "error");
        trackEvent("tez402_custom_product_create_error", { stage: "exception" });
    } finally {
        if (ui.customCreateBtn) {
            ui.customCreateBtn.disabled = false;
            ui.customCreateBtn.textContent = "CREATE PRODUCT";
        }
    }
}

function clearPaymentState() {
    cachedRequirements = null;
    activeTokenContract = null;
    activeTokenAddress = BBT_ADDRESS;
    activeTokenSymbol = "BBT";
    activeTokenDecimals = 18;
    if (ui.amount) ui.amount.innerText = "--";
    if (ui.payTo) ui.payTo.innerText = "--";
    if (ui.balance) ui.balance.innerText = "--";
    if (ui.allowance) ui.allowance.innerText = "--";
    if (ui.permit2Allowance) ui.permit2Allowance.innerText = "--";
    if (ui.permit2Expiration) ui.permit2Expiration.innerText = "--";
    if (ui.permit2Nonce) ui.permit2Nonce.innerText = "--";
    if (ui.permit2AllowanceRow) ui.permit2AllowanceRow.classList.add("hidden");
    if (ui.payBtn) {
        ui.payBtn.disabled = true;
        ui.payBtn.innerText = "5. SIGN & PAY";
    }
    setStepStatus(3, "pending", "Not started");
    setStepStatus(4, "pending", "Not started");
    setStepStatus(5, "pending", "Not started");
    setResponsePreview(ui.requirementsResponse, "Awaiting response...");
    setResponsePreview(ui.settleResponse, "Awaiting response...");
    updateTokenDetailsDisplay();
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
    const fallbackPathRaw = (item.path || "").toString().trim();
    const fallbackPath = fallbackPathRaw
        ? (fallbackPathRaw.startsWith("/") ? fallbackPathRaw : `/${fallbackPathRaw}`)
        : null;

    if (!raw) {
        return fallbackPath ? normalizeEndpointUrl(`${baseUrl}${fallbackPath}`, "") : null;
    }

    if (raw.startsWith("http://") || raw.startsWith("https://")) {
        const normalizedAbsolute = normalizeEndpointUrl(raw, "");
        if (normalizedAbsolute) {
            return normalizedAbsolute;
        }
        if (fallbackPath) {
            return normalizeEndpointUrl(`${baseUrl}${fallbackPath}`, "");
        }
        return null;
    }

    const normalizedPath = raw.startsWith("/") ? raw : `/${raw}`;
    return normalizeEndpointUrl(`${baseUrl}${normalizedPath}`, "");
}

function getCatalogCreatorAddress() {
    return userAddress ? normalizeAddress(userAddress) : null;
}

function renderCatalog(items, currentStoreUrl, preferredSelectionUrl = "") {
    catalogItems = Array.isArray(items) ? items : [];
    if (!ui.catalogSelect || !ui.catalogRow) {
        return;
    }

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
    const preferred = (preferredSelectionUrl || "").toLowerCase();
    const current = (currentStoreUrl || "").toLowerCase();

    catalogItems.forEach((item) => {
        const option = document.createElement("option");
        option.value = item.url;
        const amount = item.payment && item.payment.amount ? item.payment.amount : "--";
        const id = item.id || "item";
        const name = item.name || item.description || item.path || item.url;
        option.innerText = `${id}: ${name} (${amount})`;
        ui.catalogSelect.appendChild(option);
        if (preferred && item.url && item.url.toLowerCase() === preferred) {
            selectedValue = item.url;
        }
        if (!selectedValue && item.url && item.url.toLowerCase() === current) {
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

async function refreshCatalog(preferredSelectionUrl = "") {
    const baseUrl = getStoreBaseUrl();
    if (!baseUrl) {
        if (ui.catalogRow) ui.catalogRow.classList.add("hidden");
        catalogItems = [];
        return;
    }

    const catalogUrlObject = new URL(`${baseUrl}/api/catalog`);
    const creatorAddress = getCatalogCreatorAddress();
    if (creatorAddress) {
        catalogUrlObject.searchParams.set("creator", creatorAddress);
    }
    const catalogUrl = catalogUrlObject.toString();
    trackEvent("tez402_catalog_request", { creator_scoped: Boolean(creatorAddress) });
    try {
        const resp = await fetch(catalogUrl, { cache: "no-store" });
        if (!resp.ok) {
            if (ui.catalogRow) ui.catalogRow.classList.add("hidden");
            catalogItems = [];
            log(`CATALOG UNAVAILABLE (${resp.status}); USING DIRECT STORE URL`, "info");
            trackEvent("tez402_catalog_error", { status: resp.status });
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
                    url: normalizedUrl
                };
            })
            .filter(Boolean);

        if (normalizedItems.length === 0) {
            if (ui.catalogRow) ui.catalogRow.classList.add("hidden");
            catalogItems = [];
            log("CATALOG HAS NO USABLE PRODUCTS; USING DIRECT STORE URL", "info");
            trackEvent("tez402_catalog_load", { item_count: 0, creator_scoped: Boolean(creatorAddress) });
            return;
        }

        renderCatalog(normalizedItems, getStoreUrl(), preferredSelectionUrl);
        log(`CATALOG LOADED (${normalizedItems.length} ITEM${normalizedItems.length > 1 ? "S" : ""})`, "success");
        trackEvent("tez402_catalog_load", { item_count: normalizedItems.length, creator_scoped: Boolean(creatorAddress) });
    } catch (err) {
        if (ui.catalogRow) ui.catalogRow.classList.add("hidden");
        catalogItems = [];
        log(`CATALOG LOOKUP FAILED: ${err.message}`, "error");
        trackEvent("tez402_catalog_error", { reason: "request_failed" });
    }
}

function onCatalogSelectionChanged() {
    const selectedUrl = ui.catalogSelect?.value;
    if (!selectedUrl) {
        return;
    }
    const selectedItem = catalogItems.find((item) => item.url === selectedUrl);
    ui.storeInput.value = selectedUrl;
    clearPaymentState();
    log(`CATALOG ITEM SELECTED: ${selectedUrl}`, "info");
    trackEvent("tez402_catalog_select", { product_id: selectedItem?.id || "unknown" });
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

function formatExpiry(seconds) {
    if (!seconds || seconds === 0) {
        return "--";
    }
    const date = new Date(seconds * 1000);
    return date.toISOString().replace("T", " ").replace("Z", " UTC");
}

function getPermit2Token() {
    const accept = getActivePaymentAccept();
    const asset = normalizeAddress(accept && accept.asset ? accept.asset : "");
    if (asset) {
        return asset;
    }
    return BBT_ADDRESS;
}

function getSpenderForPermit2() {
    const raw = (ui.spenderInput?.value || "").trim() || DEFAULT_X402_EXACT_PERMIT2_PROXY_ADDRESS;
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

function trimFormattedAmount(value) {
    if (!value.includes(".")) {
        return value;
    }
    const trimmed = value.replace(/0+$/, "").replace(/\.$/, "");
    return trimmed || "0";
}

function getPaymentDisplay(accept) {
    const raw = accept && (accept.amount || accept.maxAmountRequired);
    const symbol = (accept && accept.extra && accept.extra.name) || activeTokenSymbol || "TOKEN";
    if (!raw) {
        return { amountText: "--", symbolText: symbol, buttonText: "5. SIGN & PAY" };
    }

    let amountText = raw.toString();
    try {
        const decimalsRaw =
            accept &&
            accept.extra &&
            (accept.extra.decimals ?? accept.extra.assetDecimals ?? accept.extra.tokenDecimals);
        const decimals = Number.isFinite(Number(decimalsRaw)) ? Number(decimalsRaw) : 18;
        amountText = trimFormattedAmount(ethers.formatUnits(BigInt(raw.toString()), decimals));
    } catch (err) {
        amountText = raw.toString();
    }

    return {
        amountText,
        symbolText: symbol,
        buttonText: `5. SIGN & PAY ${amountText} ${symbol}`
    };
}

function updateApproveButton(erc20Allowance) {
    const required = getRequiredAmount();
    if (!ui.approveBtn) {
        return;
    }

    if (!required || required <= 0n) {
        ui.approveBtn.disabled = true;
        ui.approveBtn.innerText = "GET PAYMENT FIRST";
        setStepStatus(4, "pending", "Waiting for step 3");
        return;
    }

    const sufficient = erc20Allowance >= required;
    if (sufficient) {
        ui.approveBtn.disabled = true;
        ui.approveBtn.innerText = "APPROVED";
        setStepStatus(4, "success", "Ready/Complete");
        return;
    }

    ui.approveBtn.disabled = false;
    ui.approveBtn.innerText = erc20Allowance > 0n ? "SET EXACT APPROVAL" : "APPROVE EXACT AMOUNT";
    setStepStatus(4, "pending", "Action required");
}

async function fetchPaymentRequirements() {
    const url = getStoreUrl();
    if (!url) {
        log("VALID STORE URL REQUIRED (HTTPS OR LOCALHOST HTTP)", "error");
        setStepStatus(3, "error", "Invalid URL");
        trackEvent("tez402_get_payment_error", { stage: "invalid_store_url" });
        return;
    }
    clearPaymentState();

    try {
        setStepStatus(3, "active", "In progress");
        log(`REQUESTING PAYMENT REQUIREMENTS: ${url}`, "info");
        trackEvent("tez402_get_payment_attempt", { source: "step3" });
        const resp = await fetch(url);
        if (resp.status !== 402) {
            setResponsePreview(ui.requirementsResponse, `Expected 402, got ${resp.status}`);
            setStepStatus(3, "error", "Expected 402");
            log(`EXPECTED 402, GOT ${resp.status}`, "error");
            trackEvent("tez402_get_payment_error", { stage: "unexpected_status", status: resp.status });
            return;
        }

        const header = resp.headers.get("payment-required") || resp.headers.get("Payment-Required");
        if (!header) {
            setStepStatus(3, "error", "Missing header");
            log("MISSING Payment-Required HEADER", "error");
            trackEvent("tez402_get_payment_error", { stage: "missing_header" });
            return;
        }

        const decoded = JSON.parse(fromBase64(header));
        cachedRequirements = decoded;
        setResponsePreview(ui.requirementsResponse, decoded);

        const accept = decoded.accepts && decoded.accepts[0];
        if (!accept) {
            setStepStatus(3, "error", "No options");
            log("NO PAYMENT OPTIONS FOUND", "error");
            trackEvent("tez402_get_payment_error", { stage: "no_accepts" });
            return;
        }

        const assetTransferMethod = accept.extra && accept.extra.assetTransferMethod;
        if (assetTransferMethod && assetTransferMethod !== "permit2") {
            setStepStatus(3, "error", "Unsupported method");
            log(`UNSUPPORTED assetTransferMethod: ${assetTransferMethod} (expected permit2)`, "error");
            if (ui.payBtn) ui.payBtn.disabled = true;
            trackEvent("tez402_get_payment_error", { stage: "unsupported_method" });
            return;
        }

        const payTo = accept.payTo;
        activeTokenAddress = getPermit2Token();
        activeTokenSymbol = getActiveTokenSymbolFromAccept(accept);
        activeTokenDecimals = getActiveTokenDecimalsFromAccept(accept);
        updateTokenDetailsDisplay();
        const display = getPaymentDisplay(accept);

        if (ui.amount) ui.amount.innerText = display.amountText;
        if (ui.payTo) ui.payTo.innerText = payTo || "--";
        if (ui.payBtn) {
            ui.payBtn.disabled = false;
            ui.payBtn.innerText = display.buttonText;
        }

        if (signer) {
            await loadTokenData();
        }

        setStepStatus(3, "success", "Complete");
        log("PAYMENT REQUIREMENTS LOADED", "success");
        trackEvent("tez402_get_payment_success", { asset_method: assetTransferMethod || "permit2" });
    } catch (err) {
        setStepStatus(3, "error", "Error");
        log(`FAILED TO GET REQUIREMENTS: ${err.message}`, "error");
        trackEvent("tez402_get_payment_error", { stage: "exception" });
    }
}

async function signAndPay() {
    trackEvent("tez402_sign_pay_click", { source: "step5" });
    if (!cachedRequirements) {
        log("GET PAYMENT REQUIREMENTS FIRST", "error");
        setStepStatus(5, "error", "Missing step 3");
        trackEvent("tez402_sign_pay_error", { stage: "missing_requirements" });
        return;
    }

    const ready = await ensureWalletConnected();
    if (!ready) {
        log("WALLET NOT CONNECTED", "error");
        setStepStatus(5, "error", "Wallet required");
        trackEvent("tez402_sign_pay_error", { stage: "wallet_not_ready" });
        return;
    }

    const accept = getActivePaymentAccept();
    if (!accept) {
        log("NO ACCEPTED PAYMENT OPTION FOUND", "error");
        setStepStatus(5, "error", "No payment option");
        return;
    }

    const assetTransferMethod = accept.extra && accept.extra.assetTransferMethod;
    if (assetTransferMethod && assetTransferMethod !== "permit2") {
        log(`UNSUPPORTED assetTransferMethod: ${assetTransferMethod} (expected permit2)`, "error");
        setStepStatus(5, "error", "Unsupported method");
        return;
    }

    const tokenAddress = normalizeAddress(accept.asset || "");
    if (!tokenAddress) {
        log("INVALID TOKEN ADDRESS IN PAYMENT REQUIREMENT", "error");
        setStepStatus(5, "error", "Invalid token");
        return;
    }
    const payTo = normalizeAddress(accept.payTo || "");
    if (!payTo) {
        log("INVALID PAYTO ADDRESS IN PAYMENT REQUIREMENT", "error");
        setStepStatus(5, "error", "Invalid payTo");
        return;
    }
    const amountRaw = accept.amount || accept.maxAmountRequired;
    let amount;
    try {
        amount = BigInt(amountRaw);
    } catch (err) {
        log("INVALID AMOUNT IN PAYMENT REQUIREMENT", "error");
        setStepStatus(5, "error", "Invalid amount");
        return;
    }
    if (amount <= 0n) {
        log("PAYMENT AMOUNT MUST BE GREATER THAN ZERO", "error");
        setStepStatus(5, "error", "Invalid amount");
        return;
    }

    if (!activeTokenContract || activeTokenAddress.toLowerCase() !== tokenAddress.toLowerCase()) {
        await loadTokenData();
    }
    if (!activeTokenContract) {
        log("TOKEN CONTRACT NOT READY", "error");
        setStepStatus(5, "error", "Token unavailable");
        return;
    }

    const acceptedRequirement = JSON.parse(JSON.stringify(accept));

    const spender = getSpenderForPermit2();
    if (!spender) {
        log("VALID SPENDER REQUIRED. CLICK CHECK /HEALTH OR ENTER A VALID X402 PROXY ADDRESS.", "error");
        setStepStatus(5, "error", "Invalid spender");
        return;
    }

    try {
        setStepStatus(5, "active", "In progress");
        const decimals = Number.isFinite(activeTokenDecimals) ? activeTokenDecimals : 18;
        const erc20Allowance = await activeTokenContract.allowance(userAddress, PERMIT2_ADDRESS);
        if (erc20Allowance < amount) {
            log("ALLOWANCE TOO LOW. APPROVE PERMIT2 FIRST.", "error");
            setStepStatus(5, "error", "Approve required");
            return;
        }

        const domain = {
            name: "Permit2",
            chainId: ETHERLINK_CHAIN_ID,
            verifyingContract: PERMIT2_ADDRESS
        };

        const now = Math.floor(Date.now() / 1000);
        const maxTimeoutSecondsRaw = accept.maxTimeoutSeconds;
        const maxTimeoutSeconds = Number.isFinite(Number(maxTimeoutSecondsRaw))
            ? Number(maxTimeoutSecondsRaw)
            : 60;
        if (maxTimeoutSeconds <= 0) {
            log(`INVALID maxTimeoutSeconds: ${maxTimeoutSecondsRaw}`, "error");
            setStepStatus(5, "error", "Invalid timeout");
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

        const paymentDisplay = getPaymentDisplay(accept);
        const irreversibleWarning = [
            "This payment is irreversible. You will not get these tokens back.",
            `Amount: ${paymentDisplay.amountText} ${paymentDisplay.symbolText}`,
            `Token: ${tokenAddress}`,
            `Pay To: ${payTo}`,
            "Press OK to continue to final signature."
        ].join("\n");
        const confirmed = window.confirm(irreversibleWarning);
        if (!confirmed) {
            setStepStatus(5, "pending", "Cancelled");
            log("SIGN/PAY CANCELLED AT IRREVERSIBLE WARNING", "info");
            trackEvent("tez402_sign_pay_confirm_cancelled", { source: "warning_modal" });
            return;
        }

        log("SIGNING PERMIT2 (WITNESS)...", "info");
        const signature = await signer.signTypedData(domain, types, value);

        const payload = {
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
        const headers = {
            "Payment-Signature": header,
            "X-GAS-PAYER": gasPayerMode
        };

        const storeUrl = getStoreUrl();
        if (!storeUrl) {
            log("VALID STORE URL REQUIRED (HTTPS OR LOCALHOST HTTP)", "error");
            setStepStatus(5, "error", "Invalid store URL");
            return;
        }

        log("SENDING Payment-Signature...", "info");
        trackEvent("tez402_sign_pay_submitted", { source: "step5" });
        const resp = await fetch(storeUrl, { headers });
        const bodyText = await resp.text();

        let responsePreview = bodyText;
        try {
            responsePreview = JSON.parse(bodyText);
        } catch (err) {
            // keep text
        }
        setResponsePreview(ui.settleResponse, responsePreview);

        if (!resp.ok) {
            log(`PAYMENT FAILED: HTTP ${resp.status}`, "error");
            log(`RESPONSE: ${bodyText}`, "error");
            setStepStatus(5, "error", `HTTP ${resp.status}`);
            trackEvent("tez402_sign_pay_error", { stage: "payment_failed", status: resp.status });
            return;
        }

        log("PAYMENT SENT. RESPONSE RECEIVED", "success");
        setStepStatus(5, "success", "Complete");
        trackEvent("tez402_sign_pay_success", { source: "step5" });

        if (ui.amount) {
            ui.amount.innerText = ethers.formatUnits(amount, decimals);
        }
    } catch (err) {
        setStepStatus(5, "error", "Error");
        log(`SIGN/PAY FAILED: ${err.message}`, "error");
        trackEvent("tez402_sign_pay_error", { stage: "exception" });
    }
}

// Start
if (document.readyState === "loading") {
    window.addEventListener("DOMContentLoaded", init);
} else {
    init();
}
