from pathlib import Path
import subprocess
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def render(*options):
    result = subprocess.run(["helm", "template", "connector", str(ROOT), *options],
        capture_output=True, text=True, check=True)
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def deployments(documents):
    return [document for document in documents if document["kind"] == "Deployment"
            and document["metadata"]["name"] in {"dil-connector", "dil-connector-management"}]


class KeyManifestTests(unittest.TestCase):
    def test_rendering_does_not_generate_keys_or_change_manifests(self):
        self.assertEqual(render(), render())

    def test_both_services_require_the_same_shared_key(self):
        documents = render()
        services = deployments(documents)
        self.assertEqual(len(services), 2)
        for service in services:
            env = service["spec"]["template"]["spec"]["containers"][0]["env"]
            refs = [value["valueFrom"]["secretKeyRef"] for value in env if value["name"].startswith("DCP_")]
            self.assertEqual(len(refs), 4)
            self.assertEqual({ref["name"] for ref in refs}, {"dil-connector-dcp-key"})
            self.assertTrue(all(not ref.get("optional", False) for ref in refs))

    def test_bootstrap_hook_lifecycle_and_rbac(self):
        documents = render()
        job = next(document for document in documents if document["kind"] == "Job")
        annotations = job["metadata"]["annotations"]
        self.assertEqual(annotations["argocd.argoproj.io/hook"], "Sync")
        self.assertIn("BeforeHookCreation", annotations["argocd.argoproj.io/hook-delete-policy"])
        self.assertEqual(annotations["helm.sh/hook"], "pre-install,pre-upgrade")
        self.assertIn("before-hook-creation", annotations["helm.sh/hook-delete-policy"])
        self.assertEqual(job["spec"]["template"]["spec"]["serviceAccountName"], "dil-connector-key-bootstrap")
        account = next(document for document in documents if document["kind"] == "ServiceAccount"
                       and document["metadata"]["name"] == "dil-connector-key-bootstrap")
        self.assertEqual(account["imagePullSecrets"], [{"name": "ghcr-pull-secret"}])
        role = next(document for document in documents if document["kind"] == "Role")
        self.assertEqual(role["rules"], [
            {"apiGroups": [""], "resources": ["secrets"], "resourceNames": ["dil-connector-dcp-key"], "verbs": ["get", "patch"]},
            {"apiGroups": [""], "resources": ["secrets"], "verbs": ["create"]},
        ])
        script = next(document for document in documents if document["kind"] == "ConfigMap"
                      and document["metadata"]["name"] == "dil-connector-key-bootstrap")
        self.assertIn("def ensure_secret", script["data"]["bootstrap_dcp_keys.py"])
        self.assertFalse(any(document["kind"] == "Secret" and document["metadata"]["name"] == "dil-connector-dcp-key" for document in documents))

    def test_external_secret_and_custom_name(self):
        documents = render("--set", "dcp.keySecret.create=false", "--set", "dcp.keySecret.name=operator-managed-key")
        self.assertFalse(any(document["kind"] in {"Job", "Role", "RoleBinding"} for document in documents))
        for service in deployments(documents):
            refs = [entry["valueFrom"]["secretKeyRef"] for entry in service["spec"]["template"]["spec"]["containers"][0]["env"] if entry["name"].startswith("DCP_")]
            self.assertEqual({ref["name"] for ref in refs}, {"operator-managed-key"})

    def test_dcp_disabled_has_no_key_dependency(self):
        documents = render("--set", "dcp.enabled=false")
        self.assertFalse(any(document["kind"] == "Job" for document in documents))
        for service in deployments(documents):
            self.assertFalse(any(entry["name"].startswith("DCP_") for entry in service["spec"]["template"]["spec"]["containers"][0]["env"]))

    def test_single_algorithm_has_only_its_required_entries(self):
        documents = render("--set", "dcp.keyAlgorithms={EdDSA}", "--set", "dcp.signingAlgorithm=EdDSA")
        for service in deployments(documents):
            names = {entry["name"] for entry in service["spec"]["template"]["spec"]["containers"][0]["env"] if entry["name"].startswith("DCP_")}
            self.assertEqual(names, {"DCP_ED25519_PRIVATE_KEY_PEM", "DCP_ED25519_KEY_ID"})

    def test_created_registry_secret_precedes_private_bootstrap_job(self):
        documents = render("--set", "registry.pullSecret.create=true", "--set", "registry.pullSecret.username=test-user",
                           "--set", "registry.pullSecret.password=test-token")
        secret = next(document for document in documents if document["kind"] == "Secret" and document["metadata"]["name"] == "ghcr-pull-secret")
        annotations = secret["metadata"]["annotations"]
        self.assertEqual(annotations["argocd.argoproj.io/hook"], "Sync")
        self.assertLess(int(annotations["argocd.argoproj.io/sync-wave"]), 0)
        self.assertLess(int(annotations["helm.sh/hook-weight"]), 0)
