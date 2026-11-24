# FirecREST compute deployment plan

Status: the split compute API/worker is available as opt-in chart values
(`dataplane.compute`, see [below](#split-compute-api-and-worker)). The other
sections are proposed requirements. Do not enable an adapter or paid offer by
copying invented configuration keys.

Architecture: [generic FirecREST dataplane](https://github.com/Data-Space-Lab/Firecrest-docker/blob/main/docs/dataplane/architecture.md).
Implementation contract: [DIL source](https://github.com/Data-Space-Lab/DIL-Connector-source/blob/main/Documentation/Architecture/firecrest-compute-extension.md).
Tasks: [Firecrest-Dataplane project](https://github.com/orgs/Data-Space-Lab/projects/3).

## P0 test infrastructure (plan 15)

Provide a reproducible API-driven test setup with two participants, separate
consumer/provider S3 storage, a worker and dedicated PostgreSQL job/event/outbox
schema. Configure private FirecREST access and dedicated execution identity,
isolated job workspaces, migrations and readiness from the first test. Keep
backend credentials, database and administrative routes private; publish only
authorized job gateway and scoped transfer routes through TLS.

Verify cluster-reachable transfer URLs independently of Docker service names and
loopback addresses. Use supported FirecREST file APIs or an approved scoped helper.
No Docker socket, privileged nested Docker or MinIO root credentials belong in
consumer-facing workloads. Explicit zero-price pilot terms still enforce resource
and concurrency quotas. A clean setup must support worker restart recovery and
the early CPU acceptance slice without GUI/GPU/AI dependencies.

Add provider reference-artifact fixtures as plan 13 lands: immutable registry and
manifest metadata, private storage locations, verified read-only cluster replicas
and distinct tenant-private uploads. A local replica skips consumer re-upload;
initial provider-to-cluster staging is still possible and measurable. Partially
copied/corrupt replicas must not become usable. Active version pins block eviction.

## Operational hardening (plan 09)

Persist and back up jobs, events/outbox, resolved manifests, artifact versions,
replica metadata, active pins and commercial usage/reservation evidence. A restore
must preserve consistent bindings and deduplication identities. Verify restored
replica bytes against digests before use. Keep durable state, storage and caches
under the provider's designated persistent deployment paths, separate from
per-job workspaces. Size staging/cache capacity and enforce quotas/retention.

Monitor stage/queue/execution latency, cache hits/misses, actual transfer bytes,
retries, scheduler accounting and correlated agreement/job/session/attempt IDs.
Retain successful execution during output delivery retry. Readiness/capacity
failure must deny unsafe admission. Test backup restoration, cancellation,
revocation, cleanup and retention with active jobs.

## Offer activation gates

Plan 16 proves CPU execution using a provider reference artifact and consumer
input, with verified binary output delivery between two connectors. It also
covers provider-only/consumer-only jobs, replacements, pinned versions, tenant
denial and crash/retry cases. Full production hardening is not a prerequisite
for starting this isolated test, but production readiness requires plan 12.

Read-only artifact mounts protect integrity, not confidentiality. Restricted
provider artifacts require controlled workloads and reviewed trust/egress/output
policy. Arbitrary custom code is initially limited to consumer-owned or explicitly
exportable inputs unless a separately reviewed trust model allows otherwise.

Paid offers remain disabled until plan 14 validates versioned charging terms,
atomic quotas/budget reservations, enforceable execution/storage/transfer caps,
deduplicated metering and settlement integration behavior. A usage event is not
proof of payment. DeepSeek/YOLO profiles are independent additions after generic
CPU acceptance, not deployment prerequisites.

## Provider bootstrap without known consumers (DIL Connector task #3)

With the matching task #3 source image, provider startup no longer requires
preconfigured consumer output destinations. This change is implemented in the
source runtime, not a new Helm value or automatically provisioned worker.

- Configure the real FirecREST execution backend, dedicated execution identities,
  compute database, signing/authority credentials, policy and input staging.
- For workloads that collect results, configure **provider-owned output staging**
  using the source repository's
  [output-staging.json](https://github.com/Data-Space-Lab/DIL-Connector-source/blob/main/Dataplane/examples/output-staging.json).
  Set the private worker `outputConfigurationFile` to that protected file. Omit
  `destinations` or use `[]`. No consumer DID, destination bucket/prefix, storage
  credentials file or fabricated `compute-output-delivery.json` is required.
- A profile containing exclusively offers that permit only `execution-only` can
  omit `outputConfigurationFile` altogether. `provider-only` retains verified
  declared outputs at the provider and still needs real staging storage.
- Drain legacy collected-but-undelivered outputs with the old worker first.
  Migration 009 cannot prove their original consumer credentials and deliberately
  denies delivery for collections without a credential fingerprint. Do not
  silently backfill these with replacement keys.
- Apply source migrations 001–009 explicitly before starting the updated API and
  worker. Migration 009 adds private runtime output bindings and the
  `NOT_REQUIRED` output-transfer state. Grant API/worker roles DML on the new
  `output_bindings` and `output_registration_keys` tables. Treat the bindings table
  and database backups as secrets because it stores scoped consumer credentials.
- Deploy matching Connector management and dataplane API/worker versions. Normal
  startup performs a schema readiness check and does not apply migrations.
  Back up before migrating; rollback requires stopping writers and restoring the
  matching pre-upgrade database before running older images.

GUI provider validation shows “No consumer destinations provisioned yet” as a
runtime delivery condition while reporting valid provider configuration. This
local validation does not prove live backend/worker connectivity. Consumer
registration does not edit the provider configuration, invalidate bound data
sources or require an API/worker restart.

After negotiation, the consumer provides its output destination and scoped
credentials through the authenticated runtime registration flow. An independent,
finalized output-sharing agreement must bind the participant, compute agreement,
exact offer/workload versions and destination. The private Connector authority
checks original/finalized agreement snapshots, parties, dataspace, expiry and both
agreements' policy/payment. Compute permission alone does not authorize output
sharing. The destination must additionally satisfy the provider-controlled HTTPS
origin/public-IP policy; an empty origin allowlist allows startup and denies all
consumer delivery.

The consumer calls `POST /compute/v1alpha1/output-destinations` with its negotiated
session capability and idempotency key, or uses its authenticated Connector
management operation `register-output`. The result exposes only a destination
reference and bounded expiry. That reference is selected at job admission.
Credentials/target/evidence are immutable; delivery retries use the original
binding and exact collected manifest. Revoked, expired, mismatched or missing
permissions fail closed. Replacing credentials or storage scope requires a new
reference and job, not mutation of an accepted job.

Non-delivery jobs require an explicit `allowedOutputModes` entry in a newly
versioned immutable offer and a matching `JobRequest.outputMode`. They cannot be
selected merely by omitting a destination. On success they report execution/job
`SUCCEEDED`, output transfer `NOT_REQUIRED` and no consumer delivery receipt.
The default/omitted mode remains consumer delivery with a mandatory independently
authorized destination.

See the source [runtime output runbook](https://github.com/Data-Space-Lab/DIL-Connector-source/blob/main/Dataplane/COMPUTE-OUTPUTS.md#provider-startup-and-runtime-destinations-dil-connector-task-3)
for exact consent and registration payloads, credential handling, migration and
rollback. Do not copy demonstration consumer credentials into chart values,
ConfigMaps or provider profiles. No live deployment is changed by these docs.

## Split compute API and worker

Kubernetes half of
[DIL-Connector-source#73](https://github.com/Data-Space-Lab/DIL-Connector-source/issues/73).
The Compose reference is `Dataplane/deploy/compute/` in the source repository.
The full procedure, helper key and storage bootstrap are in its
[deployment runbook](https://github.com/Data-Space-Lab/DIL-Connector-source/blob/main/Documentation/Architecture/runtime-output-deployment-runbook.md).

With `dataplane.compute.enabled=false` (the default) the chart renders exactly
as before. Enabled, it renders:

| Object | Role |
| --- | --- |
| `Deployment/dil-connector-dataplane` | Compute API and the ordinary dataplane. Pod label `app.kubernetes.io/component=dataplane`. Selector unchanged. |
| `Deployment/dil-connector-compute-worker` | `python -m dataplane.compute.worker`, `dataplane.compute.worker.replicas` pods, label `app.kubernetes.io/component=compute-worker`. No Service. |
| `Job/dil-connector-compute-migrate` | `python -m dataplane.compute.worker --migrate` with the migration-owner DSN. Helm `pre-install,pre-upgrade` hook and Argo CD `Sync` hook in wave `-1`, so it finishes before either Deployment rolls. |
| `NetworkPolicy/dil-connector-compute-worker` | Optional: no ingress; egress to DNS and the rules you list. |

[`values-compute-example.yaml`](../values-compute-example.yaml) shows every
value with placeholders:

```bash
helm template connector . -f values-compute-example.yaml
```

### Same image and same settings

- `dataplane.compute.image.digest` is required and must be `sha256:…`. API,
  worker, migration Job and their init containers all use
  `<repository>@<digest>`. `dataplane.image.tag` is ignored while compute is
  enabled.
- `sourceRevision` and `imageRevision` are set as
  `DIL_CONNECTOR_SOURCE_REVISION` / `DIL_CONNECTOR_IMAGE_REVISION` in every pod.
  Use the image's own values, or `compare` reports a mismatch.
- The plain settings in `dataplane.compute.env` (policy, signing key, FirecREST
  config and profiles paths, driver factory) and `DATAPLANE_CONFIG_PATH` are
  identical in all pods. The worker mounts the API's settings PVC
  (`worker.mountSettingsVolume`). That PVC is ReadWriteOnce, so the worker must
  run on the API's node (`dataplane.nodeName`) unless you switch it to a
  ReadWriteMany storage class.
- All pods carry `checksum/compute-config`, a hash of the image, revisions,
  `configVersion`, Secret/ConfigMap names, env and host aliases. A change to any
  of them rolls API and worker together. Both Deployments use `Recreate`, so two
  releases never run side by side. Worker replicas and resources are not in the
  hash.
- Helm cannot see the contents of Secrets it does not own. When you change a
  protected file, either create a new Secret name (`dil-compute-protected-v2`)
  or bump `configVersion`. Otherwise the pods keep the old copy.

### Secrets and protected files

Create these out of band. The chart only references them by name:

| Value | Contents |
| --- | --- |
| `protectedSecret` | One key per protected file: `compute-provider-policy.json`, `firecrest-worker.json`, `compute-signing.pem`, `compute-helper-signing.pem`, staging/output credentials, Keycloak client secret and JWKS, … (the names your `firecrest-worker.json` and profiles reference). |
| `settingsConfigMap` | Optional, e.g. `compute-provider-profiles.json`. |
| `runtimeEnvSecret` | `envFrom` for API and worker: runtime-role `DATAPLANE_COMPUTE_DATABASE_URL`, `DATAPLANE_AUTHORITY_TOKEN`, `DATAPLANE_COMPUTE_CONTROL_TOKEN`, `DATAPLANE_COMPUTE_SIGNING_KEY_ID`, `DATAPLANE_COMPUTE_ISSUER`, `DATAPLANE_COMPUTE_AUDIENCE` (see `compute-runtime.env.example`). `DATAPLANE_CONTROLLER_TOKEN` comes from the chart's controller Secret. |
| `migration.envSecret` | Only the migration-owner `DATAPLANE_COMPUTE_DATABASE_URL`. Mounted in the migration Job only. |
| `worker.helperSsh.secretName` | `compute-tenant-ssh-key` and `compute-known-hosts`, copied for the worker only. |

```bash
kubectl -n dil-connector create secret generic dil-compute-protected-v1 \
  --from-file=<secrets-dir>/compute-provider-policy.json \
  --from-file=<secrets-dir>/firecrest-worker.json \
  --from-file=<secrets-dir>/compute-signing.pem
kubectl -n dil-connector create secret generic dil-compute-runtime-env \
  --from-env-file=<private-dir>/compute-runtime.env
kubectl -n dil-connector create secret generic dil-compute-migration-env \
  --from-env-file=<private-dir>/compute-migration.env
kubectl -n dil-connector create secret generic dil-compute-helper-ssh \
  --from-file=<secrets-dir>/compute-tenant-ssh-key \
  --from-file=<secrets-dir>/compute-known-hosts
```

The dataplane rejects protected files that are symlinks or readable by group or
others. Kubernetes Secret and ConfigMap volumes are symlinks into `..data`, so
they cannot be mounted at `/run/secrets` directly. An init container from the
same image copies each file into an in-memory `emptyDir` as a regular `0400`
file. The main container mounts that directory read-only at `/run/secrets`, the
path the Compose reference uses. The dataplane image runs as root. If you add a
`runAsUser`, the copies are owned by that user and remain private.

### Tenant workspace, helper SSH and egress

- `worker.workspaces` mounts the tenant workspace, artifact cache and output
  snapshots at the **identical** absolute path the FirecREST helper and Slurm
  use. The default is a `hostPath` of type `Directory`. It fails to start if the
  directory is missing on that node. Pin the worker to nodes that have the paths
  with `worker.nodeName`, `nodeSelector` or `affinity`. An `existingClaim`
  works only if that volume exposes the same files the helper sees at that path.
- The helper key's `authorized_keys` line has `from="…"`. Pod IPs change, so
  `from=` cannot name a pod. Use one of these:
  - an egress gateway with a fixed SNAT address (select it with
    `worker.podLabels`), and put that address in `from=`;
  - `worker.hostNetwork: true`, and put the node addresses in `from=`.
    NetworkPolicy does not apply to host-network pods, so the chart refuses to
    render both.
- `dataplane.compute.hostAliases` replaces Compose `extra_hosts`: pin the
  public Connector name to the front proxy (NAT hairpin) and `helper.host` to
  the address that reaches the helper's sshd.
- `worker.networkPolicy` denies ingress and allows DNS plus `egress`. List the
  helper sshd, FirecREST, the compute PostgreSQL, S3 staging and the Connector
  authority origin.

### Database roles

Run migrations with a migration owner and the services with a separate runtime
role. Never give the runtime pods the owner DSN. As the schema owner, with the
actual role names substituted:

```sql
GRANT USAGE ON SCHEMA dil_compute TO "<compute-runtime-role>";
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA dil_compute
  TO "<compute-runtime-role>";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA dil_compute
  TO "<compute-runtime-role>";
REVOKE INSERT, UPDATE, DELETE ON dil_compute.schema_versions
  FROM "<compute-runtime-role>";

-- Tables and sequences created by later migrations (run as the owner role).
ALTER DEFAULT PRIVILEGES FOR ROLE "<compute-migration-owner>" IN SCHEMA dil_compute
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "<compute-runtime-role>";
ALTER DEFAULT PRIVILEGES FOR ROLE "<compute-migration-owner>" IN SCHEMA dil_compute
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO "<compute-runtime-role>";
```

Default privileges cover only tables the owner creates later. If a migration
creates `schema_versions` again, repeat the `REVOKE`. `inspect` reports
`DATABASE_GRANTS_MISSING` with each missing `table:PRIVILEGE`.

### Upgrade order

1. Pause provider admission, drain or cancel nonterminal work, back up the
   compute database.
2. Set the new `image.digest`, `sourceRevision`, `imageRevision`, and new
   Secret names or `configVersion`.
3. Sync. The migration Job runs first. If it fails, the sync stops and the old
   API and worker keep running. Read the logs with
   `kubectl -n dil-connector logs job/dil-connector-compute-migrate`. The Job is
   kept until the next sync.
4. API and worker roll together. Then run the parity check below.

`migration.mountSettingsVolume` mounts the settings PVC in the Job, for
profiles managed in the GUI. The PVC does not exist before the first install,
so enable it only after that.

### Parity check across all worker pods

`kubectl exec deployment/…` picks one arbitrary pod. Capture every worker:

```bash
ns=dil-connector
kubectl -n "$ns" get pods -l 'app.kubernetes.io/component in (dataplane,compute-worker)' \
  -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.containerStatuses[*].imageID}{"\n"}{end}'

evidence_dir=$(mktemp -d)
api_pod=$(kubectl -n "$ns" get pods -l app.kubernetes.io/component=dataplane \
  --field-selector=status.phase=Running -o name | head -n 1)
kubectl -n "$ns" exec "$api_pod" -c dil-connector-dataplane -- \
  python -m dataplane.compute.diagnostics inspect --component api \
  > "$evidence_dir/api.json"
worker_args=()
for pod in $(kubectl -n "$ns" get pods -l app.kubernetes.io/component=compute-worker -o name); do
  name=${pod#pod/}
  kubectl -n "$ns" exec "$pod" -c compute-worker -- \
    python -m dataplane.compute.diagnostics inspect --component worker \
    > "$evidence_dir/worker-$name.json"
  worker_args+=(--worker "/tmp/diagnostics/worker-$name.json")
done

# Compare in a pod running the same image, within --max-age-seconds of capture.
kubectl -n "$ns" exec "$api_pod" -c dil-connector-dataplane -- mkdir -p /tmp/diagnostics
for file in "$evidence_dir"/*.json; do
  kubectl -n "$ns" exec -i "$api_pod" -c dil-connector-dataplane -- \
    sh -c "cat > /tmp/diagnostics/${file##*/}" < "$file"
done
kubectl -n "$ns" exec "$api_pod" -c dil-connector-dataplane -- \
  python -m dataplane.compute.diagnostics compare \
  --api /tmp/diagnostics/api.json "${worker_args[@]}"
kubectl -n "$ns" exec "$api_pod" -c dil-connector-dataplane -- rm -rf /tmp/diagnostics
rm -rf "$evidence_dir"
```

`compare` exits zero only for `READY`. The number of `--worker` arguments must
equal `worker.replicas`. A pending or crashing worker is a parity failure; do
not skip it. Record which pod name maps to which `worker[n]` position.
