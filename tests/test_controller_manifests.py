import base64
import sys
import unittest
from copy import deepcopy
from pathlib import Path

from test_key_bootstrap import Store
from test_key_manifests import render

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bootstrap_controller_token as bootstrap


def controller_objects(documents):
    return [
        d
        for d in documents
        if d["metadata"]["name"] == "dil-connector-controller-bootstrap"
    ]


class ControllerSecretTests(unittest.TestCase):
    def test_bootstrap_is_stable_and_preserves_unrelated_fields(self):
        store = Store()
        self.assertEqual(
            bootstrap.ensure_secret(store, "controller-auth", "tenant"), "created"
        )
        original = deepcopy(store.secret)
        bootstrap.validate(original["data"]["controller-token"])
        store.secret["data"]["unrelated"] = base64.b64encode(b"preserve-me").decode()
        for _ in range(4):
            self.assertEqual(
                bootstrap.ensure_secret(store, "controller-auth", "tenant"), "reused"
            )
        self.assertEqual(
            store.secret["data"]["controller-token"],
            original["data"]["controller-token"],
        )
        self.assertEqual(store.creates, 1)
        self.assertIn("unrelated", store.secret["data"])

    def test_invalid_existing_controller_token_is_not_rotated(self):
        for value in ["", base64.b64encode(b"short").decode(), "invalid base64"]:
            store = Store(
                {
                    "metadata": {"resourceVersion": "1"},
                    "data": {"controller-token": value},
                }
            )
            with self.assertRaises(RuntimeError):
                bootstrap.ensure_secret(store, "controller-auth", "tenant")
            self.assertEqual(store.secret["data"]["controller-token"], value)
            self.assertEqual(store.patches, 0)

    def test_missing_key_extends_existing_secret_without_changing_other_roles(self):
        store = Store(
            {
                "metadata": {"resourceVersion": "1"},
                "data": {"existing-role": "retained"},
            }
        )
        self.assertEqual(
            bootstrap.ensure_secret(store, "controller-auth", "tenant"), "extended"
        )
        self.assertEqual(store.secret["data"]["existing-role"], "retained")
        bootstrap.validate(store.secret["data"]["controller-token"])

    def test_create_race_reads_and_preserves_the_winner(self):
        store = Store()
        original_create = store.create

        def race(document):
            original_create(document)
            return False

        store.create = race
        self.assertEqual(
            bootstrap.ensure_secret(store, "controller-auth", "tenant"), "reused"
        )
        self.assertEqual(store.creates, 1)

    def test_rendering_is_deterministic_and_three_services_share_required_secret(self):
        documents = render()
        self.assertEqual(documents, render())
        found = {}
        for d in documents:
            if d["kind"] != "Deployment":
                continue
            for c in d["spec"]["template"]["spec"]["containers"]:
                for value in c.get("env", []):
                    if value["name"] == "DATAPLANE_CONTROLLER_TOKEN":
                        found[d["metadata"]["name"]] = value["valueFrom"][
                            "secretKeyRef"
                        ]
        self.assertEqual(
            set(found),
            {"dil-connector", "dil-connector-management", "dil-connector-dataplane"},
        )
        self.assertTrue(
            all(
                v
                == {"name": "dil-connector-controller-auth", "key": "controller-token"}
                for v in found.values()
            )
        )
        self.assertFalse(
            any(
                d["kind"] == "Secret"
                and d["metadata"]["name"] == "dil-connector-controller-auth"
                for d in documents
            )
        )

    def test_controller_bootstrap_is_independent_of_dcp_and_externally_manageable(self):
        documents = render("--set", "dcp.enabled=false")
        self.assertTrue(any(d["kind"] == "Job" for d in controller_objects(documents)))
        documents = render(
            "--set",
            "dataPlane.controllerSecret.create=false",
            "--set",
            "dataPlane.controllerSecret.name=external-controller",
        )
        self.assertFalse(controller_objects(documents))
        for d in documents:
            if d["kind"] == "Deployment":
                for c in d["spec"]["template"]["spec"]["containers"]:
                    for v in c.get("env", []):
                        if v["name"] == "DATAPLANE_CONTROLLER_TOKEN":
                            self.assertEqual(
                                v["valueFrom"]["secretKeyRef"]["name"],
                                "external-controller",
                            )

    def test_controller_job_has_narrow_rbac_and_private_image_pull_configuration(self):
        documents = controller_objects(render())
        role = next(d for d in documents if d["kind"] == "Role")
        self.assertEqual(
            role["rules"],
            [
                {
                    "apiGroups": [""],
                    "resources": ["secrets"],
                    "resourceNames": ["dil-connector-controller-auth"],
                    "verbs": ["get", "patch"],
                },
                {"apiGroups": [""], "resources": ["secrets"], "verbs": ["create"]},
            ],
        )
        job = next(d for d in documents if d["kind"] == "Job")
        self.assertEqual(
            job["metadata"]["annotations"]["helm.sh/hook"], "pre-install,pre-upgrade"
        )
        account = next(d for d in documents if d["kind"] == "ServiceAccount")
        self.assertEqual(account["imagePullSecrets"], [{"name": "ghcr-pull-secret"}])
        script = next(d for d in documents if d["kind"] == "ConfigMap")
        self.assertIn("bootstrap_controller_token.py", script["data"])

    def test_old_values_without_controller_settings_use_secure_defaults(self):
        import shutil
        import subprocess
        import tempfile

        import yaml

        with tempfile.TemporaryDirectory() as directory:
            chart = Path(directory) / "chart"
            shutil.copytree(
                ROOT, chart, ignore=shutil.ignore_patterns(".git", "__pycache__")
            )
            values = yaml.safe_load((chart / "values.yaml").read_text())
            del values["dataPlane"]["controllerSecret"]
            (chart / "values.yaml").write_text(yaml.safe_dump(values))
            result = subprocess.run(
                ["helm", "template", "old-values", str(chart)],
                capture_output=True,
                text=True,
                check=True,
            )
            documents = [d for d in yaml.safe_load_all(result.stdout) if d]
            self.assertTrue(
                any(d["kind"] == "Job" for d in controller_objects(documents))
            )
            service = next(
                d
                for d in documents
                if d["kind"] == "Deployment"
                and d["metadata"]["name"] == "dil-connector-management"
            )
            entry = next(
                v
                for v in service["spec"]["template"]["spec"]["containers"][0]["env"]
                if v["name"] == "DATAPLANE_CONTROLLER_TOKEN"
            )
            self.assertEqual(
                entry["valueFrom"]["secretKeyRef"]["name"],
                "dil-connector-controller-auth",
            )
