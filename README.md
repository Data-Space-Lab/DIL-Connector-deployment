# DIL Connector Deployment

Helm and Argo CD manifests for deploying the DIL Connector from:

```text
ghcr.io/data-space-lab/dil-connector:latest
ghcr.io/data-space-lab/dil-connector-dataplane:latest
```

The deployment starts:

- `dil-connector` on port `8282` for DSP/DCP traffic
- `dil-connector-management` on port `8283` for management API traffic
- `dil-connector-dataplane` on port `8284` for negotiated data transfers
- `dil-connector-postgres` with a persistent volume

## Private GHCR Image Pulls

Keep the GHCR token out of this Git repository. Create a Kubernetes image pull
secret in the same namespace as the Pods:

```bash
kubectl create namespace dil-connector
kubectl create secret docker-registry ghcr-pull-secret \
  --namespace dil-connector \
  --docker-server=ghcr.io \
  --docker-username=<github-username> \
  --docker-password=<github-token> \
  --docker-email=<email>
```

For a private GHCR image, use a GitHub personal access token classic with at
least `read:packages`. If your GitHub organization enforces SSO, authorize the
token for that organization.

The `dil-connector` ServiceAccount references `ghcr-pull-secret`, so the Pods
can pull the private image once that Secret exists.

### Provision through Argo CD

The chart can create the pull Secret during an Argo sync. In the Argo CD UI,
open the `dil-connector` application, choose **Details**, edit **Parameters**,
and add these Helm parameters:

```text
registry.pullSecret.create=true
registry.pullSecret.username=<github-username>
registry.pullSecret.password=<github-token>
```

The chart will create the configured Secret in the connector namespace and the
ServiceAccount will automatically use it for the connector, management API,
and dataplane Pods. This keeps the token out of Git, but the value is still stored in the
Argo Application override and should only be used where Argo administrators
are trusted. For production, create the Secret externally or use a secret
operator, then leave `registry.pullSecret.create=false`.

## Deploy With ManagementAPI

Use `application-catalog-entry.json` as the ManagementAPI deployable
application payload. ManagementAPI renders tenant placeholders in
`helm_values`, so each tenant gets its own public route, DSP endpoint, and DID
values.

For tenant `material`, the catalog entry renders values such as:

```text
connector.publicHost=dil-connector.material.dil.collab-cloud.eu
catalog.participantId=did:web:dil-connector.material.dil.collab-cloud.eu:identity
catalog.serviceEndpointUrl=https://dil-connector.material.dil.collab-cloud.eu/api/dsp
```

These values are deployment-owned identity values. They should not be edited in
the GUI catalog creation form.

## Deploy With Helm

```bash
helm upgrade --install dil-connector . \
  --namespace dil-connector \
  --create-namespace \
  --set connector.publicHost=dil-connector.example.org \
  --set connector.publicBaseUrl=https://dil-connector.example.org
```

## Deploy With ArgoCD

Push this folder to GitHub, then update `argocd-application.yaml`:

- `spec.source.repoURL`
- `spec.source.targetRevision`
- `spec.source.path`

Apply the ArgoCD application:

```bash
kubectl apply -f argocd-application.yaml
```

## Things To Adjust

- `values.yaml` or ManagementAPI `helm_values`: connector image tag, connector
  IDs, public endpoint URL, DID values, callback settings, Keycloak settings,
  and catalog values. The connector and management API use the same
  `image.tag`; update it only here.
- `dataplane.rcloneEnabled`: enables the rclone adapter. The default image
  contains the rclone binary, and the S3-compatible remote can be configured
  from the GUI's **Dataplane Config** page.
- `dataplane.rcloneConfigPath`: path for the generated rclone configuration;
  it must be on the persistent dataplane config volume.
- MQTT is provided by the dataplane image's Mosquitto process. The chart
  exposes `mqtt-consumer` (1883) and `mqtt-provider` (1885) as native TCP
  service ports. Set `dataplane.mqttPublicProviderUrl` and
  `dataplane.mqttPublicConsumerUrl` to externally reachable MQTT URLs, and use
  `mqttProviderListenHost`, `mqttProviderListenPort`, `mqttConsumerListenHost`,
  and `mqttConsumerListenPort` to control the native listeners. These are
  deployment settings, not GUI settings. Configure provider broker profiles
  and consumer authentication under **Dataplane Config**. `mqtt-stream` source
  forms are generated from those configured server IDs. Use a TCP load balancer
  or NodePort for these ports; HTTP ingress paths cannot carry native MQTT
  traffic.
- `dataplane.rcloneConfigSecret`: optional Kubernetes Secret name. The Secret
  must contain a `rclone.conf` key; the chart mounts it at
  `/root/.config/rclone/rclone.conf`.
- `dataplane.configStorage`: enables the persistent volume used by the GUI's
  Dataplane Config page. Native S3/MinIO connection settings are stored in
  `/data/dataplane-config.json`; secret values are not returned by the
  dataplane API. The default `1Gi` volume uses the cluster's default storage
  class, or set `dataplane.configStorage.storageClassName` explicitly.

To enable `s3-copy` through rclone, create the config Secret in the connector
namespace and set both values before committing/syncing the chart:

The preferred method is the GUI. Open **Dataplane Config**, select `rclone`,
enter the MinIO endpoint, remote name, region, and credentials, then use
**Verify connection** followed by **Save configuration**. Source data objects
can then use a remote such as `tenant-minio:dil-data/demo.csv`.

For advanced deployments with multiple remotes, the optional Secret method
remains supported:

```bash
rclone config create material-minio s3 provider Minio \
  endpoint https://minio-api.material.dil.collab-cloud.eu \
  access_key_id '<access-key>' \
  secret_access_key '<secret-key>'
rclone config file

kubectl -n dil-connector create secret generic dil-connector-rclone-config \
  --from-file=rclone.conf="$HOME/.config/rclone/rclone.conf" \
  --dry-run=client -o yaml | kubectl apply -f -
```

Then configure:

```yaml
dataplane:
  rcloneEnabled: true
  rcloneConfigSecret: dil-connector-rclone-config
```

After Argo CD syncs, verify the pod has the remote with:
`kubectl -n dil-connector exec deploy/dil-connector-dataplane -- rclone listremotes`.
- `dsp.providerDataAddresses`: configure the provider source address for each
  transfer profile used by an EDC consumer. For `s3-copy`, the EDC dataplane
  expects the provider to return an `AmazonS3` DataAddress in the DSP
  `TransferStartMessage`. Example values (replace the endpoint and credentials
  with tenant-specific values):

  ```yaml
  dsp:
    providerDataAddresses:
      s3-copy:
        type: AmazonS3
        endpoint: https://minio-api.material.dil.collab-cloud.eu
        bucketName: dil-data
        objectName: demo.csv
        region: us-east-1
        accessKeyId: REPLACE_WITH_READ_ONLY_KEY
        secretAccessKey: REPLACE_WITH_READ_ONLY_SECRET
  ```

  Do not commit real object-storage credentials to Git or a ConfigMap. Use the
  deployment platform's secret-to-values mechanism, or make the source bucket
  publicly readable where appropriate. The DIL catalog may continue to expose
  its internal `RcloneData` description; the provider transfer flow translates
  the configured source into the native EDC address required on the wire.
- DCP signing keys are bootstrapped automatically; see Shared DCP Signing Keys
  below. Both connector processes require the same persistent Secret.
- Routes are created by ManagementAPI from the application catalog entry.
- Replace the default demo database password in `values.yaml` for a real
  environment.
- Payment is disabled by default. Set `payment.enabled: true`, configure the
  tenant's `company` profile and a protected `payment.adapters` block to enable
  a provider. The connector validates customer VAT IDs through VIES and caches
  results for `payment.viesCacheTtlSeconds` seconds. Configure a public
  `payment.webhookBaseUrl` when registering provider webhooks. Do not commit
  PayPal, MobilePay or Klarna credentials to this repository; use a protected
  Helm values source or secret-rendering mechanism.

Do not commit real GHCR tokens or production database passwords to Git.

## Shared DCP Signing Keys

With DCP enabled, the chart automatically creates `dil-connector-dcp-key` in the
connector namespace using a create-once bootstrap Job. It generates PKCS#8
private keys and stable key IDs for the configured ES256 and/or EdDSA algorithms:

- ES256: `private-key.pem` and `key-id`.
- EdDSA: `ed25519-private-key.pem` and `ed25519-key-id`.

The Job runs during ArgoCD sync and Helm install/upgrade. It uses the connector
image, including its cryptography dependency, and a separate namespaced service
account. It can read/patch only the named signing Secret and create Secrets in
that namespace; it cannot delete or list Secrets. Patches only add wholly absent
algorithm pairs and require a matching resource version. No key material is placed
in Helm values, rendered manifests, Git, or logs. A concurrent create reuses the
winning Secret instead of replacing it.

Valid existing keys and IDs are reused unchanged. A wholly missing algorithm pair
is added without replacing existing keys. A partial pair or invalid key fails
bootstrap explicitly rather than rotating an identity. Both public
and management services require the same Secret entries, so a missing Secret no
longer starts two processes with unrelated in-memory keys.

For externally managed keys, set `dcp.keySecret.create=false` and optionally
`dcp.keySecret.name`. Provision all entries for the enabled algorithms before
starting the workloads. Retain and back up the Secret: deleting the namespace
also deletes its keys. Changing enabled algorithms may require an explicit
operator-managed Secret update; the bootstrap never replaces existing material.

Upgrading an existing installation that has no signing Secret creates new,
persistent keys and restarts the workloads with them. Existing peer key caches
and dataspace signing profiles may need updating to the newly published IDs.
This does not change the participant DID or reissue membership credentials.
Key rotation is a separate, explicit operation.

Validate with `python3 -m unittest discover -s tests` and `helm lint .` (Python
tests require cryptography and PyYAML, plus Helm for manifest checks).

# Grafana dataplane authorization

The Grafana adapter uses a private management authorization endpoint, not a DSP
extension. Before enabling Grafana queries, create the Secret named by
`dataPlane.authorizationSecret` (default `dil-connector-dataplane-auth`):

```bash
kubectl -n dil-connector create secret generic dil-connector-dataplane-auth \
  --from-literal=control-token="$(openssl rand -hex 32)" \
  --from-literal=grafana-client-token="$(openssl rand -hex 32)"
```

Keep these values out of Git. Missing keys disable Grafana authorization while
existing adapters remain available. The control token is shared only between the
management service and dataplane. The separate Grafana client token belongs in
the consuming Grafana plugin's secure datasource configuration. Restart the two
deployments after rotating the Secret.

Configure the Grafana adapter through Settings > Dataplanes with the provider
Grafana URL, restricted service-account token, allowed datasource UIDs, and public
query URL. Route only `/grafana/provider/` and, where required, `/grafana/consumer/`
to dataplane port 8284 without rewriting their paths. Never expose dataplane
administrative routes or management `/internal/data-plane/` publicly.

Query auditing uses `dataplane.grafanaAuditDb` on the existing `/data` PVC. Keep
one dataplane replica/worker for SQLite auditing and process-local rate limits.
Grafana queries require a FINALIZED agreement and STARTED transfer. Installing
the images alone does not configure a provider Grafana service or public routes.
