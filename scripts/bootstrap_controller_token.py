"""Create/reuse controller credentials; never rotate an existing Secret value."""

import base64
import os
import secrets
import sys

from bootstrap_dcp_keys import KubernetesSecretStore


def validate(value):
    try:
        token = base64.b64decode(value, validate=True).decode("ascii")
    except (ValueError, UnicodeError):
        raise RuntimeError(
            "Existing controller credential is invalid; refusing to replace it"
        ) from None
    if not 32 <= len(token) <= 4096 or not all(33 <= ord(c) <= 126 for c in token):
        raise RuntimeError(
            "Existing controller credential is invalid; refusing to replace it"
        )


def ensure_secret(store, name, namespace):
    for _ in range(5):
        existing = store.get()
        if existing is not None and "controller-token" in (existing.get("data") or {}):
            validate(existing["data"]["controller-token"])
            return "reused"
        value = base64.b64encode(secrets.token_urlsafe(48).encode()).decode()
        if existing is None:
            document = {
                "apiVersion": "v1",
                "kind": "Secret",
                "type": "Opaque",
                "metadata": {
                    "name": name,
                    "namespace": namespace,
                    "labels": {
                        "app.kubernetes.io/managed-by": "dil-controller-bootstrap"
                    },
                },
                "data": {"controller-token": value},
            }
            if store.create(document):
                return "created"
        elif store.add_missing(existing, {"controller-token": value}):
            return "extended"
    raise RuntimeError("Controller Secret changed repeatedly; retry setup")


if __name__ == "__main__":
    try:
        name, namespace = (
            os.environ["CONTROLLER_SECRET_NAME"],
            os.environ["POD_NAMESPACE"],
        )
        result = ensure_secret(KubernetesSecretStore(name, namespace), name, namespace)
        print("Controller credential " + result, flush=True)
    except Exception:  # noqa: BLE001 - never emit credential or Kubernetes response details
        print(
            "Controller credential bootstrap failed; check Secret permissions and existing credential format. Existing values were not rotated.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
