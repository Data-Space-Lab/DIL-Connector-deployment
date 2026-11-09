import base64
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bootstrap_keys", ROOT / "scripts" / "bootstrap_dcp_keys.py")
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class Store:
    def __init__(self, secret=None):
        self.secret = deepcopy(secret)
        self.creates = 0
        self.patches = 0

    def get(self):
        return deepcopy(self.secret)

    def create(self, secret):
        self.creates += 1
        self.secret = deepcopy(secret)
        return True

    def add_missing(self, existing, additions):
        self.patches += 1
        if any(field in self.secret["data"] for field in additions):
            return False
        self.secret["data"].update(additions)
        return True


class KeyBootstrapTests(unittest.TestCase):
    def test_api_extension_tests_version_and_only_adds_absent_fields(self):
        existing = bootstrap.new_secret("shared-key", "example", ["ES256"])
        existing["metadata"]["resourceVersion"] = "17"
        additions = bootstrap.new_secret("shared-key", "example", ["EdDSA"])["data"]
        store = bootstrap.KubernetesSecretStore.__new__(bootstrap.KubernetesSecretStore)
        store.url = "https://kubernetes.default.svc/test-secret"
        store.request = MagicMock()
        self.assertTrue(store.add_missing(existing, additions))
        method, url, operations, content_type = store.request.call_args.args
        self.assertEqual(method, "PATCH")
        self.assertEqual(content_type, "application/json-patch+json")
        self.assertEqual(operations[0], {"op": "test", "path": "/metadata/resourceVersion", "value": "17"})
        self.assertEqual({op["path"] for op in operations[1:]}, {"/data/" + key for key in additions})

    def test_api_extension_refuses_to_replace_existing_fields(self):
        existing = bootstrap.new_secret("shared-key", "example", ["ES256"])
        existing["metadata"]["resourceVersion"] = "17"
        store = bootstrap.KubernetesSecretStore.__new__(bootstrap.KubernetesSecretStore)
        store.request = MagicMock()
        with self.assertRaisesRegex(RuntimeError, "Refusing to replace"):
            store.add_missing(existing, {"private-key.pem": "replacement"})
        store.request.assert_not_called()

    def test_new_install_creates_both_valid_private_keys(self):
        store = Store()
        self.assertEqual(bootstrap.ensure_secret(store, "shared-key", "example", ["ES256", "EdDSA"]), "created")
        self.assertEqual(store.secret["metadata"]["name"], "shared-key")
        self.assertEqual(store.secret["metadata"]["namespace"], "example")
        self.assertEqual(store.secret["type"], "Opaque")
        bootstrap.validate_secret(store.secret, ["ES256", "EdDSA"])
        ec_key = serialization.load_pem_private_key(base64.b64decode(store.secret["data"]["private-key.pem"]), None)
        ed_key = serialization.load_pem_private_key(base64.b64decode(store.secret["data"]["ed25519-private-key.pem"]), None)
        self.assertIsInstance(ec_key, ec.EllipticCurvePrivateKey)
        self.assertIsInstance(ec_key.curve, ec.SECP256R1)
        self.assertIsInstance(ed_key, ed25519.Ed25519PrivateKey)

    def test_syncs_and_restarts_do_not_rotate_keys_or_ids(self):
        store = Store()
        bootstrap.ensure_secret(store, "shared-key", "example", ["ES256", "EdDSA"])
        original = deepcopy(store.secret)
        for _ in range(4):
            self.assertEqual(bootstrap.ensure_secret(store, "shared-key", "example", ["ES256", "EdDSA"]), "reused")
        self.assertEqual(store.secret, original)
        self.assertEqual(store.creates, 1)

    def test_existing_unrelated_data_is_not_modified(self):
        existing = bootstrap.new_secret("shared-key", "example", ["ES256", "EdDSA"])
        existing["data"]["operator-metadata"] = base64.b64encode(b"preserve-me").decode()
        store = Store(existing)
        bootstrap.ensure_secret(store, "shared-key", "example", ["ES256", "EdDSA"])
        self.assertEqual(store.secret, existing)
        self.assertEqual(store.creates, 0)

    def test_missing_algorithm_is_added_without_rotating_existing_keys(self):
        store = Store(bootstrap.new_secret("shared-key", "example", ["ES256"]))
        original = deepcopy(store.secret["data"])
        self.assertEqual(bootstrap.ensure_secret(store, "shared-key", "example", ["ES256", "EdDSA"]), "extended")
        self.assertEqual({key: store.secret["data"][key] for key in original}, original)
        bootstrap.validate_secret(store.secret, ["ES256", "EdDSA"])
        self.assertEqual(store.patches, 1)
        self.assertEqual(bootstrap.ensure_secret(store, "shared-key", "example", ["ES256", "EdDSA"]), "reused")

    def test_partial_existing_pair_fails_without_replacement(self):
        existing = bootstrap.new_secret("shared-key", "example", ["ES256", "EdDSA"])
        del existing["data"]["ed25519-key-id"]
        store = Store(existing)
        original = deepcopy(store.secret)
        with self.assertRaisesRegex(RuntimeError, "refusing to rotate"):
            bootstrap.ensure_secret(store, "shared-key", "example", ["ES256", "EdDSA"])
        self.assertEqual(store.secret, original)
        self.assertEqual(store.creates, 0)
        self.assertEqual(store.patches, 0)

    def test_extension_race_reuses_winning_keys(self):
        winner = bootstrap.new_secret("shared-key", "example", ["EdDSA"])["data"]

        class RacingStore(Store):
            def add_missing(self, existing, additions):
                self.secret["data"].update(winner)
                return False

        store = RacingStore(bootstrap.new_secret("shared-key", "example", ["ES256"]))
        self.assertEqual(bootstrap.ensure_secret(store, "shared-key", "example", ["ES256", "EdDSA"]), "reused")
        self.assertEqual({key: store.secret["data"][key] for key in winner}, winner)

    def test_invalid_existing_secret_fails_closed(self):
        for field, value in (("private-key.pem", "not-base64"),
                             ("private-key.pem", base64.b64encode(b"not-a-key").decode()),
                             ("key-id", base64.b64encode(b"   ").decode())):
            with self.subTest(field=field, value=value):
                existing = bootstrap.new_secret("shared-key", "example", ["ES256"])
                existing["data"][field] = value
                store = Store(existing)
                with self.assertRaises(RuntimeError):
                    bootstrap.ensure_secret(store, "shared-key", "example", ["ES256"])
                self.assertEqual(store.creates, 0)

    def test_wrong_key_algorithm_is_not_silently_replaced(self):
        existing = bootstrap.new_secret("shared-key", "example", ["ES256", "EdDSA"])
        existing["data"]["private-key.pem"] = existing["data"]["ed25519-private-key.pem"]
        store = Store(existing)
        with self.assertRaisesRegex(RuntimeError, "invalid ES256"):
            bootstrap.ensure_secret(store, "shared-key", "example", ["ES256"])
        self.assertEqual(store.creates, 0)

    def test_concurrent_create_reuses_the_winner(self):
        winner = bootstrap.new_secret("shared-key", "example", ["ES256", "EdDSA"])

        class RacingStore(Store):
            def create(self, secret):
                self.creates += 1
                self.secret = deepcopy(winner)
                return False

        store = RacingStore()
        self.assertEqual(bootstrap.ensure_secret(store, "shared-key", "example", ["ES256", "EdDSA"]), "reused")
        self.assertEqual(store.secret, winner)

    def test_single_algorithm_install_is_supported(self):
        for algorithm in ("ES256", "EdDSA"):
            with self.subTest(algorithm=algorithm):
                store = Store()
                bootstrap.ensure_secret(store, "shared-key", "example", [algorithm])
                self.assertEqual(set(store.secret["data"]), set(bootstrap.KEY_FIELDS[algorithm]))

    def test_unsupported_algorithms_do_not_create_a_secret(self):
        for algorithms in ([], ["RS256"], ["ES256", "unknown"]):
            store = Store()
            with self.assertRaisesRegex(RuntimeError, "supports ES256 and EdDSA"):
                bootstrap.ensure_secret(store, "shared-key", "example", algorithms)
            self.assertEqual(store.creates, 0)
