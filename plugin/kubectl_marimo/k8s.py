"""Kubernetes client wrapper."""

import subprocess
import sys
from typing import Any


def apply_resource(resource: dict[str, Any], dry_run: bool = False) -> bool:
    """Apply a Kubernetes resource using kubectl.

    Returns True on success, False on failure.
    """
    import yaml

    yaml_content = yaml.dump(resource, default_flow_style=False)

    if dry_run:
        print(yaml_content)
        return True

    cmd = ["kubectl", "apply", "-f", "-"]
    try:
        result = subprocess.run(
            cmd,
            input=yaml_content,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Error: {result.stderr}", file=sys.stderr)
            return False
        print(result.stdout, end="")
        return True
    except FileNotFoundError:
        print("Error: kubectl not found in PATH", file=sys.stderr)
        return False


def delete_resource(
    kind: str,
    name: str,
    namespace: str,
    ignore_not_found: bool = True,
) -> bool:
    """Delete a Kubernetes resource using kubectl."""
    cmd = ["kubectl", "delete", kind, name, "-n", namespace]
    if ignore_not_found:
        cmd.append("--ignore-not-found")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error: {result.stderr}", file=sys.stderr)
            return False
        print(result.stdout, end="")
        return True
    except FileNotFoundError:
        print("Error: kubectl not found in PATH", file=sys.stderr)
        return False


def exec_in_pod(
    pod_name: str,
    namespace: str,
    command: str,
) -> tuple[bool, str]:
    """Execute command in pod using kubectl exec.

    Returns (success, output).
    """
    cmd = [
        "kubectl",
        "exec",
        "-n",
        namespace,
        pod_name,
        "--",
        "sh",
        "-c",
        command,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return False, result.stderr
        return True, result.stdout
    except FileNotFoundError:
        return False, "kubectl not found in PATH"


def get_pod_logs(pod_name: str, namespace: str) -> tuple[bool, str]:
    """Get pod logs using kubectl logs."""
    cmd = ["kubectl", "logs", "-n", namespace, pod_name]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return False, result.stderr
        return True, result.stdout
    except FileNotFoundError:
        return False, "kubectl not found in PATH"


def patch_resource(
    kind: str,
    name: str,
    namespace: str,
    patch: str,
) -> bool:
    """Patch a Kubernetes resource using kubectl.

    Returns True on success, False on failure.
    """
    cmd = [
        "kubectl",
        "patch",
        kind,
        name,
        "-n",
        namespace,
        "--type=merge",
        "-p",
        patch,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error: {result.stderr}", file=sys.stderr)
            return False
        print(result.stdout, end="")
        return True
    except FileNotFoundError:
        print("Error: kubectl not found in PATH", file=sys.stderr)
        return False


def get_resource(
    kind: str,
    name: str,
    namespace: str,
) -> tuple[bool, dict[str, Any] | str]:
    """Get a Kubernetes resource as dict.

    Returns (success, resource_dict or error_message).
    """
    import yaml

    cmd = ["kubectl", "get", kind, name, "-n", namespace, "-o", "yaml"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return False, result.stderr
        return True, yaml.safe_load(result.stdout)
    except FileNotFoundError:
        return False, "kubectl not found in PATH"
