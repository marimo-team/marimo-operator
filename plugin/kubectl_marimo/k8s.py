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
    namespace: str | None,
    ignore_not_found: bool = True,
) -> bool:
    """Delete a Kubernetes resource using kubectl."""
    cmd = ["kubectl", "delete", kind, name]
    if namespace is not None:
        cmd.extend(["-n", namespace])
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


def resource_exists(kind: str, name: str, namespace: str | None = None) -> bool:
    """Check if a Kubernetes resource exists.

    Args:
        kind: Resource kind (e.g., "marimos.marimo.io", "pod")
        name: Resource name
        namespace: Kubernetes namespace (None = use kubectl context)

    Returns:
        True if resource exists, False otherwise
    """
    cmd = ["kubectl", "get", kind, name, "-o", "name"]
    if namespace is not None:
        cmd.extend(["-n", namespace])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def exec_in_pod(
    pod_name: str,
    namespace: str | None,
    command: str,
) -> tuple[bool, str]:
    """Execute command in pod using kubectl exec.

    Returns (success, output).
    """
    cmd = [
        "kubectl",
        "exec",
        pod_name,
        "--",
        "sh",
        "-c",
        command,
    ]
    if namespace is not None:
        cmd.insert(2, namespace)
        cmd.insert(2, "-n")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return False, result.stderr
        return True, result.stdout
    except FileNotFoundError:
        return False, "kubectl not found in PATH"


def get_pod_logs(pod_name: str, namespace: str | None) -> tuple[bool, str]:
    """Get pod logs using kubectl logs."""
    cmd = ["kubectl", "logs", pod_name]
    if namespace is not None:
        cmd.insert(2, namespace)
        cmd.insert(2, "-n")
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
    namespace: str | None,
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
        "--type=merge",
        "-p",
        patch,
    ]
    if namespace is not None:
        cmd.insert(4, namespace)
        cmd.insert(4, "-n")
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
    namespace: str | None,
) -> tuple[bool, dict[str, Any] | str]:
    """Get a Kubernetes resource as dict.

    Returns (success, resource_dict or error_message).
    """
    import yaml

    cmd = ["kubectl", "get", kind, name, "-o", "yaml"]
    if namespace is not None:
        cmd.insert(4, namespace)
        cmd.insert(4, "-n")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return False, result.stderr
        return True, yaml.safe_load(result.stdout)
    except FileNotFoundError:
        return False, "kubectl not found in PATH"
