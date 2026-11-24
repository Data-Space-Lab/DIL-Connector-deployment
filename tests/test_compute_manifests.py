import subprocess
import unittest

from test_key_manifests import ROOT, render

EXAMPLE = str(ROOT / "values-compute-example.yaml")
DIGEST = "sha256:" + "0" * 64


def find(documents, kind, name):
    matches = [d for d in documents if d["kind"] == kind and d["metadata"]["name"] == name]
    return matches[0] if matches else None


def pod(document):
    return document["spec"]["template"]["spec"]


def container(document):
    return pod(document)["containers"][0]


def env(document):
    return {entry["name"]: entry.get("value", entry.get("valueFrom")) for entry in container(document)["env"]}


def compute_documents(documents):
    return [d for d in documents
            if d["metadata"].get("labels", {}).get("app.kubernetes.io/component") in {"compute-worker", "compute-migrate"}]


class ComputeDisabledTests(unittest.TestCase):
    def test_disabled_renders_no_compute_objects(self):
        documents = render()
        self.assertEqual(compute_documents(documents), [])
        api = find(documents, "Deployment", "dil-connector-dataplane")
        self.assertNotIn("labels", api["metadata"])
        self.assertEqual(api["spec"]["template"]["metadata"], {"labels": {"app": "dil-connector-dataplane"}})
        self.assertNotIn("initContainers", pod(api))
        self.assertNotIn("envFrom", container(api))
        self.assertFalse(any(name.startswith(("DATAPLANE_COMPUTE_", "DIL_CONNECTOR_")) for name in env(api)))
        self.assertTrue(container(api)["image"].endswith(":release-20261120-4"))

    def test_compute_values_are_inert_while_disabled(self):
        # Every compute value set, only the flag off: output identical to defaults.
        self.assertEqual(render(), render("-f", EXAMPLE, "--set", "dataplane.compute.enabled=false"))
        material = str(ROOT / "values-material.yaml")
        self.assertEqual(render("-f", material),
                         render("-f", material, "-f", EXAMPLE, "--set", "dataplane.compute.enabled=false"))


class ComputeEnabledTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = render("-f", EXAMPLE)
        cls.api = find(cls.documents, "Deployment", "dil-connector-dataplane")
        cls.worker = find(cls.documents, "Deployment", "dil-connector-compute-worker")
        cls.job = find(cls.documents, "Job", "dil-connector-compute-migrate")

    def test_two_deployments_with_component_labels(self):
        self.assertIsNotNone(self.api)
        self.assertIsNotNone(self.worker)
        self.assertEqual(self.api["spec"]["template"]["metadata"]["labels"]["app.kubernetes.io/component"], "dataplane")
        self.assertEqual(self.worker["spec"]["template"]["metadata"]["labels"]["app.kubernetes.io/component"], "compute-worker")
        # Selectors stay disjoint, and the API selector is unchanged (immutable field).
        self.assertEqual(self.api["spec"]["selector"], {"matchLabels": {"app": "dil-connector-dataplane"}})
        self.assertEqual(self.worker["spec"]["selector"], {"matchLabels": {"app": "dil-connector-compute-worker"}})
        service = find(self.documents, "Service", "dil-connector-dataplane")
        self.assertEqual(service["spec"]["selector"], {"app": "dil-connector-dataplane"})
        self.assertIsNone(find(self.documents, "Service", "dil-connector-compute-worker"))

    def test_worker_replicas_and_command(self):
        self.assertEqual(self.worker["spec"]["replicas"], 2)
        self.assertEqual(self.worker["spec"]["strategy"], {"type": "Recreate"})
        self.assertEqual(container(self.worker)["command"], ["python", "-m", "dataplane.compute.worker"])
        replicas = render("-f", EXAMPLE, "--set", "dataplane.compute.worker.replicas=3")
        self.assertEqual(find(replicas, "Deployment", "dil-connector-compute-worker")["spec"]["replicas"], 3)

    def test_identical_image_and_secret_versions(self):
        image = f"ghcr.io/data-space-lab/dil-connector-dataplane@{DIGEST}"
        for document in (self.api, self.worker, self.job):
            self.assertEqual(container(document)["image"], image)
            self.assertEqual(pod(document)["initContainers"][0]["image"], image)
        api_env, worker_env = env(self.api), env(self.worker)
        shared = {name: value for name, value in worker_env.items()
                  if name.startswith(("DATAPLANE_COMPUTE_", "DIL_CONNECTOR_"))}
        self.assertEqual(shared["DIL_CONNECTOR_SOURCE_REVISION"], "<full-source-commit>")
        self.assertEqual(shared["DIL_CONNECTOR_IMAGE_REVISION"], "<immutable-release-tag>")
        for name, value in shared.items():
            self.assertEqual(api_env[name], value, name)
            self.assertEqual(env(self.job)[name], value, name)
        self.assertEqual(api_env["DATAPLANE_CONFIG_PATH"], worker_env["DATAPLANE_CONFIG_PATH"])
        self.assertEqual(container(self.api)["envFrom"], container(self.worker)["envFrom"])
        self.assertEqual(container(self.api)["envFrom"], [{"secretRef": {"name": "dil-compute-runtime-env"}}])
        annotations = [d["spec"]["template"]["metadata"]["annotations"] for d in (self.api, self.worker, self.job)]
        self.assertTrue(annotations[0]["checksum/compute-config"])
        self.assertEqual(annotations[0], annotations[1])
        self.assertEqual(annotations[0], annotations[2])

    def test_protected_files_mounted_read_only(self):
        def sources(document):
            volume = next(v for v in pod(document)["volumes"] if v["name"] == "compute-protected-source")
            return volume["projected"]["sources"]

        for document in (self.api, self.worker, self.job):
            mount = next(m for m in container(document)["volumeMounts"] if m["name"] == "compute-protected")
            self.assertEqual(mount, {"name": "compute-protected", "mountPath": "/run/secrets", "readOnly": True})
            volume = next(v for v in pod(document)["volumes"] if v["name"] == "compute-protected")
            self.assertEqual(volume["emptyDir"]["medium"], "Memory")
            self.assertEqual(sources(document)[:2], [{"secret": {"name": "dil-compute-protected-v1"}},
                                                     {"configMap": {"name": "dil-compute-settings-v1"}}])
        # Only the worker gets the helper SSH key.
        self.assertEqual(sources(self.worker)[2]["secret"]["name"], "dil-compute-helper-ssh")
        self.assertEqual(len(sources(self.api)), 2)
        self.assertEqual(len(sources(self.job)), 2)

    def test_config_change_rolls_api_and_worker_together(self):
        def checksums(*options):
            documents = render("-f", EXAMPLE, *options)
            return {name: find(documents, "Deployment", name)["spec"]["template"]["metadata"]["annotations"]["checksum/compute-config"]
                    for name in ("dil-connector-dataplane", "dil-connector-compute-worker")}

        before = checksums()
        for option in ("dataplane.compute.configVersion=2", "dataplane.compute.protectedSecret=dil-compute-protected-v2",
                       f"dataplane.compute.image.digest=sha256:{'1' * 64}"):
            after = checksums("--set", option)
            self.assertEqual(len(set(after.values())), 1, option)
            self.assertNotEqual(after, before, option)
        self.assertEqual(checksums("--set", "dataplane.compute.worker.replicas=4"), before)

    def test_worker_workspace_at_identical_host_path(self):
        mounts = {m["name"]: m["mountPath"] for m in container(self.worker)["volumeMounts"]}
        volumes = {v["name"]: v for v in pod(self.worker)["volumes"]}
        for name, path in (("tenant-workspace", "/srv/dil/tenant-a"), ("artifact-cache", "/srv/dil/artifact-cache"),
                           ("output-snapshots", "/srv/dil/output-snapshots")):
            self.assertEqual(mounts[name], path)
            self.assertEqual(volumes[name]["hostPath"], {"path": path, "type": "Directory"})
        self.assertFalse(any(m["mountPath"].startswith("/srv/") for m in container(self.api)["volumeMounts"]))
        self.assertEqual(pod(self.worker)["nodeSelector"], {"dil.example.org/compute-execution": "true"})
        self.assertFalse(pod(self.worker)["automountServiceAccountToken"])
        claim = render("-f", EXAMPLE, "--set", "dataplane.compute.worker.workspaces[0].name=tenant-workspace",
                       "--set", "dataplane.compute.worker.workspaces[0].path=/srv/dil/tenant-a",
                       "--set", "dataplane.compute.worker.workspaces[0].existingClaim=tenant-a-pvc")
        worker = find(claim, "Deployment", "dil-connector-compute-worker")
        volume = next(v for v in pod(worker)["volumes"] if v["name"] == "tenant-workspace")
        self.assertEqual(volume, {"name": "tenant-workspace", "persistentVolumeClaim": {"claimName": "tenant-a-pvc"}})

    def test_migration_job_is_a_hook_with_the_owner_dsn(self):
        annotations = self.job["metadata"]["annotations"]
        self.assertEqual(annotations["helm.sh/hook"], "pre-install,pre-upgrade")
        self.assertEqual(annotations["argocd.argoproj.io/hook"], "Sync")
        self.assertLess(int(annotations["argocd.argoproj.io/sync-wave"]), 0)
        self.assertEqual(container(self.job)["command"], ["python", "-m", "dataplane.compute.worker", "--migrate"])
        self.assertEqual(container(self.job)["envFrom"], [{"secretRef": {"name": "dil-compute-migration-env"}}])
        self.assertEqual(pod(self.job)["restartPolicy"], "Never")
        # The migration-owner Secret never reaches the long-running pods.
        for document in (self.api, self.worker):
            self.assertNotIn("dil-compute-migration-env", str(document))
        disabled = render("-f", EXAMPLE, "--set", "dataplane.compute.migration.enabled=false")
        self.assertIsNone(find(disabled, "Job", "dil-connector-compute-migrate"))

    def test_network_policy(self):
        policy = find(self.documents, "NetworkPolicy", "dil-connector-compute-worker")
        self.assertEqual(policy["spec"]["podSelector"], {"matchLabels": {"app": "dil-connector-compute-worker"}})
        self.assertEqual(policy["spec"]["ingress"], [])
        self.assertEqual(len(policy["spec"]["egress"]), 3)
        self.assertIsNone(find(render("-f", EXAMPLE, "--set", "dataplane.compute.worker.networkPolicy.enabled=false"),
                               "NetworkPolicy", "dil-connector-compute-worker"))

    def test_rejects_mutable_or_missing_image(self):
        for option in ("dataplane.compute.image.digest=", "dataplane.compute.image.digest=release-20261120-4"):
            result = subprocess.run(["helm", "template", "connector", str(ROOT), "-f", EXAMPLE, "--set", option],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0, option)
            self.assertIn("dataplane.compute.image.digest", result.stderr)


if __name__ == "__main__":
    unittest.main()
