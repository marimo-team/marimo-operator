# SSH Sidecar Example

Mount your pod's filesystem locally for bidirectional editing with your local tools.

## Use Case

- Edit notebooks locally with your preferred IDE while they run in the cluster
- Sync files bidirectionally between local machine and pod
- Access pod filesystem without kubectl cp

## Quick Start

```bash
# 1. Create secret with your SSH public key
kubectl create secret generic ssh-pubkey \
  --from-file=authorized_keys=~/.ssh/id_ed25519.pub

# 2. Deploy the notebook
kubectl apply -f notebook.yaml

# 3. Port-forward SSH
kubectl port-forward svc/ssh-notebook 2222:2222 &

# 4. Mount locally via sshfs
mkdir -p ./notebooks
sshfs marimo@localhost:/home/marimo/notebooks ./notebooks -p 2222

# 5. Edit files locally - changes sync to pod automatically
```

## Using kubectl-marimo Plugin

The plugin handles all of this automatically:

```bash
kubectl marimo deploy notebook.py --source sshfs:///home/marimo/notebooks
```

## Manual SSH Access

If sshfs isn't installed, you can still SSH directly:

```bash
ssh -p 2222 marimo@localhost -i ~/.ssh/id_ed25519
```
