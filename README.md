# DIL Connector Deployment

Kustomize and ArgoCD manifests for deploying the DIL Connector from:

```text
ghcr.io/data-space-lab/dil.-connector:latest
```

The deployment starts:

- `dil-connector` on port `8282` for DSP/DCP traffic
- `dil-connector-management` on port `8283` for management API traffic
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

## Deploy With Kustomize

```bash
kubectl apply -k .
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

- `configmap.yaml`: connector IDs, public endpoint URL, DID values, callback
  settings, Keycloak settings, catalog values.
- `route.yaml`: hostname and gateway namespace/name.
- `postgres-secret.yaml`: replace the default demo database password for a real
  environment.

Do not commit real GHCR tokens or production database passwords to Git.
