// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/*
Flattened single-file source for Blockscout verification.

Deployed on Etherlink at:
- 0xB6FD384A0626BfeF85f3dBaf5223Dd964684B09E

Verification settings used for the deployment build:
- Compiler: solc 0.8.28
- Optimizer: enabled, runs=200
- EVM version: cancun
- viaIR: false

Contract to verify: x402ExactPermit2Proxy
*/

// -----------------------------------------------------------------------------
// OpenZeppelin StorageSlot (v5.1.0) - inlined
// -----------------------------------------------------------------------------

/**
 * @dev Library for reading and writing primitive types to specific storage slots.
 */
library StorageSlot {
    struct AddressSlot {
        address value;
    }

    struct BooleanSlot {
        bool value;
    }

    struct Bytes32Slot {
        bytes32 value;
    }

    struct Uint256Slot {
        uint256 value;
    }

    struct Int256Slot {
        int256 value;
    }

    struct StringSlot {
        string value;
    }

    struct BytesSlot {
        bytes value;
    }

    function getAddressSlot(bytes32 slot) internal pure returns (AddressSlot storage r) {
        assembly ("memory-safe") {
            r.slot := slot
        }
    }

    function getBooleanSlot(bytes32 slot) internal pure returns (BooleanSlot storage r) {
        assembly ("memory-safe") {
            r.slot := slot
        }
    }

    function getBytes32Slot(bytes32 slot) internal pure returns (Bytes32Slot storage r) {
        assembly ("memory-safe") {
            r.slot := slot
        }
    }

    function getUint256Slot(bytes32 slot) internal pure returns (Uint256Slot storage r) {
        assembly ("memory-safe") {
            r.slot := slot
        }
    }

    function getInt256Slot(bytes32 slot) internal pure returns (Int256Slot storage r) {
        assembly ("memory-safe") {
            r.slot := slot
        }
    }

    function getStringSlot(bytes32 slot) internal pure returns (StringSlot storage r) {
        assembly ("memory-safe") {
            r.slot := slot
        }
    }

    function getStringSlot(string storage store) internal pure returns (StringSlot storage r) {
        assembly ("memory-safe") {
            r.slot := store.slot
        }
    }

    function getBytesSlot(bytes32 slot) internal pure returns (BytesSlot storage r) {
        assembly ("memory-safe") {
            r.slot := slot
        }
    }

    function getBytesSlot(bytes storage store) internal pure returns (BytesSlot storage r) {
        assembly ("memory-safe") {
            r.slot := store.slot
        }
    }
}

// -----------------------------------------------------------------------------
// OpenZeppelin ReentrancyGuard (v5.5.0) - inlined
// -----------------------------------------------------------------------------

abstract contract ReentrancyGuard {
    using StorageSlot for bytes32;

    bytes32 private constant REENTRANCY_GUARD_STORAGE =
        0x9b779b17422d0df92223018b32b4d1fa46e071723d6817e2486d003becc55f00;

    uint256 private constant NOT_ENTERED = 1;
    uint256 private constant ENTERED = 2;

    error ReentrancyGuardReentrantCall();

    constructor() {
        _reentrancyGuardStorageSlot().getUint256Slot().value = NOT_ENTERED;
    }

    modifier nonReentrant() {
        _nonReentrantBefore();
        _;
        _nonReentrantAfter();
    }

    modifier nonReentrantView() {
        _nonReentrantBeforeView();
        _;
    }

    function _nonReentrantBeforeView() private view {
        if (_reentrancyGuardEntered()) {
            revert ReentrancyGuardReentrantCall();
        }
    }

    function _nonReentrantBefore() private {
        _nonReentrantBeforeView();
        _reentrancyGuardStorageSlot().getUint256Slot().value = ENTERED;
    }

    function _nonReentrantAfter() private {
        _reentrancyGuardStorageSlot().getUint256Slot().value = NOT_ENTERED;
    }

    function _reentrancyGuardEntered() internal view returns (bool) {
        return _reentrancyGuardStorageSlot().getUint256Slot().value == ENTERED;
    }

    function _reentrancyGuardStorageSlot() internal pure virtual returns (bytes32) {
        return REENTRANCY_GUARD_STORAGE;
    }
}

// -----------------------------------------------------------------------------
// IERC20Permit (OpenZeppelin v5.5.0) - minimal interface
// -----------------------------------------------------------------------------

interface IERC20Permit {
    function permit(
        address owner,
        address spender,
        uint256 value,
        uint256 deadline,
        uint8 v,
        bytes32 r,
        bytes32 s
    ) external;

    function nonces(address owner) external view returns (uint256);

    function DOMAIN_SEPARATOR() external view returns (bytes32);
}

// -----------------------------------------------------------------------------
// ISignatureTransfer (Permit2 SignatureTransfer) - inlined
// -----------------------------------------------------------------------------

interface ISignatureTransfer {
    struct TokenPermissions {
        address token;
        uint256 amount;
    }

    struct PermitTransferFrom {
        TokenPermissions permitted;
        uint256 nonce;
        uint256 deadline;
    }

    struct SignatureTransferDetails {
        address to;
        uint256 requestedAmount;
    }

    function nonceBitmap(address, uint256) external view returns (uint256);

    function permitTransferFrom(
        PermitTransferFrom memory permit,
        SignatureTransferDetails calldata transferDetails,
        address owner,
        bytes calldata signature
    ) external;

    function permitWitnessTransferFrom(
        PermitTransferFrom memory permit,
        SignatureTransferDetails calldata transferDetails,
        address owner,
        bytes32 witness,
        string calldata witnessTypeString,
        bytes calldata signature
    ) external;
}

// -----------------------------------------------------------------------------
// x402BasePermit2Proxy - inlined
// -----------------------------------------------------------------------------

abstract contract x402BasePermit2Proxy is ReentrancyGuard {
    ISignatureTransfer public PERMIT2;
    bool private _initialized;

    string public constant WITNESS_TYPE_STRING =
        "Witness witness)TokenPermissions(address token,uint256 amount)Witness(address to,uint256 validAfter,bytes extra)";

    bytes32 public constant WITNESS_TYPEHASH = keccak256("Witness(address to,uint256 validAfter,bytes extra)");

    event Settled();
    event SettledWithPermit();

    error InvalidPermit2Address();
    error AlreadyInitialized();
    error InvalidDestination();
    error PaymentTooEarly();
    error InvalidOwner();

    struct Witness {
        address to;
        uint256 validAfter;
        bytes extra;
    }

    struct EIP2612Permit {
        uint256 value;
        uint256 deadline;
        bytes32 r;
        bytes32 s;
        uint8 v;
    }

    function initialize(address _permit2) external {
        if (_initialized) revert AlreadyInitialized();
        if (_permit2 == address(0)) revert InvalidPermit2Address();
        _initialized = true;
        PERMIT2 = ISignatureTransfer(_permit2);
    }

    function _settle(
        ISignatureTransfer.PermitTransferFrom calldata permit,
        uint256 amount,
        address owner,
        Witness calldata witness,
        bytes calldata signature
    ) internal {
        if (owner == address(0)) revert InvalidOwner();
        if (witness.to == address(0)) revert InvalidDestination();
        if (block.timestamp < witness.validAfter) revert PaymentTooEarly();

        ISignatureTransfer.SignatureTransferDetails memory transferDetails =
            ISignatureTransfer.SignatureTransferDetails({to: witness.to, requestedAmount: amount});

        bytes32 witnessHash = keccak256(
            abi.encode(WITNESS_TYPEHASH, witness.to, witness.validAfter, keccak256(witness.extra))
        );

        PERMIT2.permitWitnessTransferFrom(
            permit,
            transferDetails,
            owner,
            witnessHash,
            WITNESS_TYPE_STRING,
            signature
        );
    }

    function _executePermit(address token, address owner, EIP2612Permit calldata permit2612) internal {
        try IERC20Permit(token).permit(
            owner,
            address(PERMIT2),
            permit2612.value,
            permit2612.deadline,
            permit2612.v,
            permit2612.r,
            permit2612.s
        ) {
            // permit succeeded
        } catch {
            // ignore
        }
    }
}

// -----------------------------------------------------------------------------
// x402ExactPermit2Proxy - deployed contract
// -----------------------------------------------------------------------------

contract x402ExactPermit2Proxy is x402BasePermit2Proxy {
    function settle(
        ISignatureTransfer.PermitTransferFrom calldata permit,
        address owner,
        Witness calldata witness,
        bytes calldata signature
    ) external nonReentrant {
        _settle(permit, permit.permitted.amount, owner, witness, signature);
        emit Settled();
    }

    function settleWithPermit(
        EIP2612Permit calldata permit2612,
        ISignatureTransfer.PermitTransferFrom calldata permit,
        address owner,
        Witness calldata witness,
        bytes calldata signature
    ) external nonReentrant {
        _executePermit(permit.permitted.token, owner, permit2612);
        _settle(permit, permit.permitted.amount, owner, witness, signature);
        emit SettledWithPermit();
    }
}
