# Capability contracts

`services/` groups service capability interfaces by domain. `servers/` holds
server capability interfaces, including backend and health contracts. The
capability enums live alongside their respective interfaces.

The existing `mlox.service` and `mlox.server` modules re-export these objects;
legacy imports and persisted references remain valid. New code can import from
`mlox.contracts.services` or `mlox.contracts.servers` directly. Contracts must
not depend on concrete service or server implementations; use type-only imports
when a type reference would introduce a dependency cycle.

`AbstractFirewallServer` defines the complete server firewall capability:
servers propose and validate their own policies, describe fixed rules, report
typed status, and implement apply, disable, and persistence. Implementations
must advertise `ServerCapability.FIREWALL` only when they support the full
contract. K3s does not currently advertise it. A server may expose an
unverified public peer candidate via `AbstractServer.firewall_peer_address()`;
the caller must not treat this as proof of reachability or a static address.
