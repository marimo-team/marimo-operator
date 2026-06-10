# marimo-operator Helm chart

Installs the [marimo-operator](https://github.com/marimo-team/marimo-operator) — a Kubernetes
operator that manages `MarimoNotebook` custom resources — including its CRD, controller
`Deployment`, and RBAC.

## Prerequisites

- Kubernetes >= 1.21
- Helm 3
- Permission to create cluster-scoped resources (CRD, ClusterRole) on first install

## Install

```sh
helm install marimo-operator ./deploy/charts/marimo-operator \
  --namespace marimo-operator-system --create-namespace
```

The operator installs into the release namespace — set `--namespace` to deploy it anywhere.

Pin a specific operator image:

```sh
helm install marimo-operator ./deploy/charts/marimo-operator \
  --namespace marimo-operator-system --create-namespace \
  --set image.tag=v0.3.0
```

## CRD lifecycle

The `MarimoNotebook` CRD ships in the chart's `crds/` directory. Helm installs it on first
install but **does not upgrade or delete it** on `helm upgrade` / `helm uninstall`. When a new
operator release changes the CRD, apply it manually:

```sh
kubectl apply -f https://raw.githubusercontent.com/marimo-team/marimo-operator/<tag>/deploy/charts/marimo-operator/crds/marimo.io_marimos.yaml
```

The CRD is generated from the Go API types by `make manifests` and copied into the chart by the
same target, so it stays in lockstep with `config/crd/bases`.

## Values

| Key | Default | Description |
|-----|---------|-------------|
| `replicaCount` | `1` | Operator replicas (leader election elects the active one). |
| `image.repository` | `ghcr.io/marimo-team/marimo-operator` | Controller image repository. |
| `image.tag` | `""` | Image tag; defaults to the chart `appVersion`. |
| `image.pullPolicy` | `IfNotPresent` | Image pull policy. |
| `imagePullSecrets` | `[]` | Image pull secrets. |
| `nameOverride` / `fullnameOverride` | `""` | Override generated resource names. |
| `serviceAccount.create` | `true` | Create the controller ServiceAccount. |
| `serviceAccount.name` | `""` | ServiceAccount name (generated when empty). |
| `serviceAccount.annotations` | `{}` | ServiceAccount annotations (e.g. IRSA). |
| `rbac.create` | `true` | Create ClusterRole/Role and bindings. |
| `leaderElection.enabled` | `true` | Enable leader election. |
| `healthProbe.bindAddress` | `:8081` | Health probe bind address. |
| `metrics.enabled` | `true` | Serve the controller metrics endpoint. |
| `metrics.bindAddress` | `:8443` | Metrics bind address. |
| `metrics.secure` | `true` | Serve metrics over HTTPS with authn/authz. |
| `metrics.enableHTTP2` | `false` | Enable HTTP/2 on the metrics server. |
| `metrics.service.type` | `ClusterIP` | Metrics Service type. |
| `metrics.service.port` | `8443` | Metrics Service port. |
| `metrics.serviceMonitor.enabled` | `false` | Create a Prometheus Operator ServiceMonitor. |
| `metrics.serviceMonitor.labels` | `{}` | Extra ServiceMonitor labels (e.g. Prometheus release selector). |
| `metrics.serviceMonitor.interval` | `""` | Scrape interval. |
| `metrics.serviceMonitor.scrapeTimeout` | `""` | Scrape timeout. |
| `metrics.serviceMonitor.insecureSkipVerify` | `true` | Skip TLS verification when scraping. |
| `metrics.serviceMonitor.tlsConfig` | `{}` | Full `tlsConfig` override (replaces `insecureSkipVerify`). |
| `networkPolicy.enabled` | `false` | Restrict metrics ingress with a NetworkPolicy. |
| `networkPolicy.metricsPort` | `8443` | Metrics port allowed by the policy. |
| `networkPolicy.fromNamespaceLabels` | `{metrics: enabled}` | Namespace selector allowed to scrape. |
| `operatorImages.initImage` | `busybox:1.36` | `DEFAULT_INIT_IMAGE` env. |
| `operatorImages.gitImage` | `alpine/git:latest` | `GIT_IMAGE` env. |
| `operatorImages.alpineImage` | `alpine:latest` | `ALPINE_IMAGE` env. |
| `operatorImages.s3fsImage` | `ghcr.io/marimo-team/marimo-operator/s3fs:latest` | `S3FS_IMAGE` env. |
| `extraArgs` | `[]` | Extra controller args. |
| `extraEnv` | `[]` | Extra controller env. |
| `extraVolumes` / `extraVolumeMounts` | `[]` | Extra volumes / mounts. |
| `resources` | req `10m`/`64Mi`, lim `500m`/`128Mi` | Controller resources. |
| `livenessProbe` / `readinessProbe` | see `values.yaml` | Controller probes. |
| `podSecurityContext` | `runAsNonRoot`, `RuntimeDefault` | Pod security context. |
| `securityContext` | restricted | Container security context. |
| `terminationGracePeriodSeconds` | `10` | Pod termination grace period. |
| `podAnnotations` / `podLabels` | `{}` | Extra pod annotations / labels. |
| `nodeSelector` / `tolerations` / `affinity` / `topologySpreadConstraints` | empty | Scheduling controls. |
| `priorityClassName` | `""` | Pod priority class. |
