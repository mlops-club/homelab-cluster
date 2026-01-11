#!/usr/bin/env -S uv run --with pyyaml -- python
"""
Refresh kubeconfig user credentials from remote cluster node.
Preserves the server configuration while updating only the user credentials.
"""

import subprocess
import yaml
import sys
from pathlib import Path
from datetime import datetime

SSH_USER = "main"
SSH_HOST = "cluster-node-1"
REMOTE_KUBECONFIG = "/etc/rancher/k3s/k3s.yaml"
LOCAL_KUBECONFIG = Path.home() / ".kube" / "config"

def main():
    print(f"Fetching kubeconfig from {SSH_USER}@{SSH_HOST}...")
    
    temp_remote = f"/tmp/k3s-config-{datetime.now().strftime('%Y%m%d%H%M%S')}.yaml"
    try:
        # Step 1: Copy to temp file on remote (passwordless sudo required)
        subprocess.run(
            ["ssh", f"{SSH_USER}@{SSH_HOST}", f"sudo cp {REMOTE_KUBECONFIG} {temp_remote} && sudo chmod 644 {temp_remote}"],
            check=True
        )
        # Step 2: Fetch the temp file (no sudo needed)
        result = subprocess.run(
            ["ssh", f"{SSH_USER}@{SSH_HOST}", f"cat {temp_remote}"],
            capture_output=True,
            text=True,
            check=True
        )
        # Step 3: Clean up remote temp file
        subprocess.run(
            ["ssh", f"{SSH_USER}@{SSH_HOST}", f"rm -f {temp_remote}"],
            capture_output=True
        )
        remote_config = yaml.safe_load(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error: Failed to fetch kubeconfig", file=sys.stderr)
        # Try to clean up on error
        subprocess.run(["ssh", f"{SSH_USER}@{SSH_HOST}", f"rm -f {temp_remote}"], capture_output=True)
        sys.exit(1)
    
    # Extract user credentials
    if not remote_config.get("users") or not remote_config["users"][0].get("user"):
        print("Error: Remote kubeconfig missing user credentials", file=sys.stderr)
        sys.exit(1)
    
    new_user = remote_config["users"][0]
    
    # Load local config
    try:
        with open(LOCAL_KUBECONFIG, "r") as f:
            local_config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: {LOCAL_KUBECONFIG} not found", file=sys.stderr)
        sys.exit(1)
    
    # Backup
    backup_path = LOCAL_KUBECONFIG.with_suffix(f".backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    subprocess.run(["cp", str(LOCAL_KUBECONFIG), str(backup_path)], check=True)
    print(f"Backed up current config to: {backup_path}")
    
    # Update only the user credentials (preserve server/cluster config)
    local_config["users"][0] = new_user
    
    # Write updated config
    with open(LOCAL_KUBECONFIG, "w") as f:
        yaml.dump(local_config, f, default_flow_style=False, sort_keys=False)
    
    LOCAL_KUBECONFIG.chmod(0o600)
    print("Successfully updated kubeconfig user credentials")
    
    # Verify
    print("Verifying connection...")
    try:
        result = subprocess.run(["kubectl", "get", "nodes"], capture_output=True, text=True, check=True)
        print("✓ kubectl connection verified successfully")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"✗ kubectl connection failed: {e.stderr}", file=sys.stderr)
        print(f"Restore backup with: cp {backup_path} {LOCAL_KUBECONFIG}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
