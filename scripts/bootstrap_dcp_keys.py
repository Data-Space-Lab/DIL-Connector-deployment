"""Create stable shared DCP keys once, without rotating existing identities."""

import base64
import json
import os
from pathlib import Path
import ssl
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519


KEY_FIELDS = {
    "ES256": ("private-key.pem", "key-id"),
    "EdDSA": ("ed25519-private-key.pem", "ed25519-key-id"),
}


def validate_secret(secret, algorithms):
    data = secret.get("data") or {}
    for algorithm in algorithms:
        pem_field, id_field = KEY_FIELDS[algorithm]
        if not data.get(pem_field) or not data.get(id_field):
            raise RuntimeError(f"Existing signing Secret is missing {pem_field} or {id_field}; refusing to rotate keys")
        try:
            pem = base64.b64decode(data[pem_field], validate=True)
            key_id = base64.b64decode(data[id_field], validate=True).decode("utf-8").strip()
            key = serialization.load_pem_private_key(pem, password=None)
        except (ValueError, TypeError, UnicodeError) as exc:
            raise RuntimeError(f"Existing signing Secret has invalid {algorithm} key material") from exc
        valid = (isinstance(key, ec.EllipticCurvePrivateKey) and isinstance(key.curve, ec.SECP256R1)) if algorithm == "ES256" else isinstance(key, ed25519.Ed25519PrivateKey)
        if not valid or not key_id:
            raise RuntimeError(f"Existing signing Secret has invalid {algorithm} key material or key ID")


def new_secret(name, namespace, algorithms):
    data = {}
    for algorithm in algorithms:
        key = ec.generate_private_key(ec.SECP256R1()) if algorithm == "ES256" else ed25519.Ed25519PrivateKey.generate()
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        pem_field, id_field = KEY_FIELDS[algorithm]
        data[pem_field] = base64.b64encode(pem).decode("ascii")
        data[id_field] = base64.b64encode(str(uuid4()).encode("ascii")).decode("ascii")
    return {"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
            "metadata": {"name": name, "namespace": namespace,
                         "labels": {"app.kubernetes.io/managed-by": "dil-connector-key-bootstrap"}},
            "data": data}


def ensure_secret(store, name, namespace, algorithms):
    algorithms = list(dict.fromkeys(algorithms))
    if not algorithms or any(algorithm not in KEY_FIELDS for algorithm in algorithms):
        raise RuntimeError("Automatic signing-key bootstrap supports ES256 and EdDSA only")
    for _ in range(5):
        existing = store.get()
        if existing is None:
            if store.create(new_secret(name, namespace, algorithms)):
                return "created"
            continue
        missing = []
        for algorithm in algorithms:
            fields = KEY_FIELDS[algorithm]
            if any(field in (existing.get("data") or {}) for field in fields):
                validate_secret(existing, [algorithm])
            else:
                missing.append(algorithm)
        if not missing:
            return "reused"
        additions = new_secret(name, namespace, missing)["data"]
        # Add only wholly absent algorithm pairs. Resource-version testing
        # prevents a concurrent sync from overwriting another writer's keys.
        if store.add_missing(existing, additions):
            return "extended"
    raise RuntimeError("Signing Secret changed repeatedly; retry bootstrap")


class KubernetesSecretStore:
    def __init__(self, name, namespace):
        service_account = Path("/var/run/secrets/kubernetes.io/serviceaccount")
        self.token = (service_account / "token").read_text().strip()
        self.context = ssl.create_default_context(cafile=str(service_account / "ca.crt"))
        self.collection = "https://kubernetes.default.svc/api/v1/namespaces/" + quote(namespace, safe="") + "/secrets"
        self.url = self.collection + "/" + quote(name, safe="")

    def request(self, method, url, body=None, content_type="application/json"):
        request = Request(url, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": content_type})
        return urlopen(request, context=self.context, timeout=20)

    def get(self):
        try:
            with self.request("GET", self.url) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise RuntimeError(f"Could not read signing Secret: Kubernetes HTTP {exc.code}") from None

    def create(self, secret):
        try:
            with self.request("POST", self.collection, secret):
                return True
        except HTTPError as exc:
            if exc.code == 409:
                return False
            raise RuntimeError(f"Could not create signing Secret: Kubernetes HTTP {exc.code}") from None

    def add_missing(self, existing, additions):
        version = existing.get("metadata", {}).get("resourceVersion")
        if not version or any(key in (existing.get("data") or {}) for key in additions):
            raise RuntimeError("Refusing to replace existing signing Secret data")
        patch = [{"op": "test", "path": "/metadata/resourceVersion", "value": version}]
        if existing.get("data") is None:
            patch.append({"op": "add", "path": "/data", "value": {}})
        patch.extend({"op": "add", "path": "/data/" + key, "value": value} for key, value in additions.items())
        try:
            with self.request("PATCH", self.url, patch, "application/json-patch+json"):
                return True
        except HTTPError as exc:
            if exc.code in {409, 422}:
                return False
            raise RuntimeError(f"Could not extend signing Secret: Kubernetes HTTP {exc.code}") from None


if __name__ == "__main__":
    name = os.environ["DCP_SECRET_NAME"]
    namespace = os.environ["POD_NAMESPACE"]
    algorithms = json.loads(os.environ["DCP_KEY_ALGORITHMS"])
    result = ensure_secret(KubernetesSecretStore(name, namespace), name, namespace, algorithms)
    print(f"DCP signing Secret {name}: {result}", flush=True)
