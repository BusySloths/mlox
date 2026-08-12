# MLflow Gateway

MLflow Gateway provides a Basic Auth protected HTTPS API for loading and invoking
MLflow registry models. Models are loaded on demand and cached in memory.

## Setup

In MLOX, add an MLflow model registry first, then select one gateway service:

- `mlflow-gateway-3.8.1-docker`
- `mlflow-gateway-3.8.1-k3s`
- `mlflow-gateway-3.8.1-k3s-managed-tls`

During setup, select the registry and optionally configure additional Python
requirements, the maximum cached models, and the cache TTL.

MLOX generates gateway credentials. Docker deployments also get an external
port; k3s deployments use a generated URL path on the k3s Traefik endpoint.

The managed-TLS k3s variant additionally selects a hostname and an existing
MLOX secret-manager entry. The entry must contain the matching certificate and
private key as one structured value:

```json
{
  "tls.crt": "-----BEGIN CERTIFICATE-----...",
  "tls.key": "-----BEGIN PRIVATE KEY-----..."
}
```

Only the hostname, secret-manager service UUID, and secret name are persisted
with the gateway. The PEM values are loaded and validated during setup.

## Usage

Health check:

```bash
curl -k -u 'USER:PASSWORD' https://HOST:PORT/health
# k3s: curl -k -u 'USER:PASSWORD' https://HOST/gateway-ID/health
```

Prometheus metrics:

```bash
curl -k -u 'USER:PASSWORD' https://HOST:PORT/metrics
```

The gateway returns an `X-Request-ID` response header. Callers may supply their
own `X-Request-ID` to correlate gateway access logs with client-side telemetry.

Invoke a registered model version:

```bash
curl -k -u 'USER:PASSWORD' \
  https://HOST:PORT/prod/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "registry_model_name": "MyModel",
    "registry_model_version": "1",
    "input_data": [[1, 2, 3]],
    "params": {}
  }'
```

The API also supports model aliases and cache inspection at `/cache`.

## Docker

The Docker service builds the gateway image locally and starts a dedicated
Traefik container on an automatically assigned MLOX port.

Advantages:

- Fast restarts after the image has been built.
- Simple lifecycle through Docker Compose.
- Isolated network and Traefik instance per gateway.

Pitfalls:

- Requires Docker and local image build capacity.
- Additional requirements trigger an image rebuild.
- Traefik mounts the Docker socket read-only.

## Kubernetes / k3s

The k3s service creates an isolated namespace containing a ConfigMap, Secret,
single-replica Deployment, ClusterIP Service, Traefik middlewares, and an
Ingress. It uses the Traefik instance that k3s installs by default.

MLOX derives a gateway ID from the service UUID. A second gateway receives its
own namespace and its own path, for example `https://HOST/gateway-abc12345`.

Advantages:

- Kubernetes-native readiness, health checks, and workload recovery.
- Each gateway is isolated from the default ingress and other gateways.
- No per-gateway Traefik Helm release is installed.
- No container registry or custom image publication is required.

Pitfalls:

- The pod installs MLflow and other dependencies from PyPI at startup, so the
  first start and pod replacements are slower and require outbound access.
  During this phase MLOX reports the service as starting until the deployment
  has a ready replica and the `/health` endpoint answers.
- The k3s Traefik CRDs must be available.
- The k3s HTTPS ingress port must be allowed by the host firewall.
- Credentials are stored in a Kubernetes Secret; protect cluster access.

### Managed TLS variant

The managed-TLS variant inherits the regular k3s deployment and remains a
separate catalog entry for now. It creates one additional namespace-local
`kubernetes.io/tls` Secret and configures the existing Traefik Ingress with the
selected hostname and TLS Secret. It does not install or reconfigure Traefik.

Certificate material is retrieved through the gateway service's runtime-bound
dependency lookup. It is uploaded through protected temporary files that are
removed after the Kubernetes Secret is applied; it is not written into the
persistent gateway manifest or MLOX service state. Updating the referenced
secret and running setup again rotates the Kubernetes Secret.

Cloudflare Origin Certificates are intended for the Cloudflare-to-origin
connection. Direct clients generally do not trust them; use the Cloudflare
hostname/proxy path or a publicly trusted certificate for direct access.

## Common Limitations

- The regular Docker and k3s variants use Traefik's default self-signed
  certificate. Use `curl -k` or `verify=False`. The managed-TLS k3s variant
  uses the selected certificate instead.
- MLflow tracking TLS verification is disabled for compatibility with MLOX's
  self-signed deployments.
- The model cache is process-local and is cleared on restart.
- Both variants use one gateway process/replica; shared caching, HPA, and
  high-availability operation are not provided.
- Model-specific libraries must be included under additional requirements.
