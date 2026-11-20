# FirecREST compute deployment plan

Status: proposed requirements, not implemented chart values or service manifests.
Do not enable an adapter or paid offer by copying invented configuration keys.

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
