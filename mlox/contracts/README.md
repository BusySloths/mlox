# Capability contracts

`services/` groups service capability interfaces by domain. `servers/` holds
server capability interfaces, including backend and health contracts. The
capability enums live alongside their respective interfaces.

The existing `mlox.service` and `mlox.server` modules re-export these objects;
legacy imports and persisted references remain valid. New code can import from
`mlox.contracts.services` or `mlox.contracts.servers` directly. Contracts must
not depend on concrete service or server implementations; use type-only imports
when a type reference would introduce a dependency cycle.
