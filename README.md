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
- For DCP credential issuance, the connector must keep a stable private key
  matching the public JWK published in its DID document. Create the optional
  `dil-connector-dcp-key` Secret with `private-key.pem` and `key-id` for ES256,
  and/or `ed25519-private-key.pem` and `ed25519-key-id` for EdDSA. The chart
  mounts these values into both connector processes. Without the Secret, keys
  are generated in memory and a restart can make the published DID key and
  outgoing DCP signature disagree.
- Routes are created by ManagementAPI from the application catalog entry.
- Replace the default demo database password in `values.yaml` for a real
  environment.

Do not commit real GHCR tokens or production database passwords to Git.
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
