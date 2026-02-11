// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {x402ExactPermit2Proxy} from "./x402ExactPermit2Proxy.sol";

/// @notice Deploys x402ExactPermit2Proxy and initializes Permit2 in one transaction.
/// @dev Mitigates deploy/init race conditions for fresh deployments.
contract x402ExactPermit2ProxyFactory {
    error InvalidPermit2Address();

    event ProxyDeployed(address indexed proxy, address indexed permit2);

    function deploy(address permit2) external returns (address proxy) {
        if (permit2 == address(0)) revert InvalidPermit2Address();

        x402ExactPermit2Proxy instance = new x402ExactPermit2Proxy();
        instance.initialize(permit2);

        proxy = address(instance);
        emit ProxyDeployed(proxy, permit2);
    }
}
