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
