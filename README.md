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
- `dataplane.rcloneEnabled`: set to `true` only after rclone remotes and
  credentials are mounted/configured for the tenant.
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
- Routes are created by ManagementAPI from the application catalog entry.
- Replace the default demo database password in `values.yaml` for a real
  environment.

Do not commit real GHCR tokens or production database passwords to Git.
