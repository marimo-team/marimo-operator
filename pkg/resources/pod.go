package resources

import (
	"encoding/json"
	"fmt"
	"strings"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/strategicpatch"

	marimov1alpha1 "github.com/marimo-team/marimo-operator/api/v1alpha1"
	"github.com/marimo-team/marimo-operator/pkg/config"
)

const (
	// NotebookDir is the directory where notebooks are stored.
	NotebookDir = "/home/marimo/notebooks"
	// DefaultMode is the default mode for running marimo.
	DefaultMode = "edit"
)

// BuildPod creates a Pod spec for a MarimoNotebook.
// Supports two content modes:
// - source: clone from git URL
// - content: mount from ConfigMap (created by operator)
func BuildPod(notebook *marimov1alpha1.MarimoNotebook) *corev1.Pod {
	var initContainers []corev1.Container
	var volumeMounts []corev1.VolumeMount
	var volumes []corev1.Volume

	// Use PVC if storage is configured, otherwise emptyDir
	if notebook.Spec.Storage != nil {
		volumes = []corev1.Volume{
			{
				Name: PVCVolumeName,
				VolumeSource: corev1.VolumeSource{
					PersistentVolumeClaim: &corev1.PersistentVolumeClaimVolumeSource{
						ClaimName: notebook.Name,
					},
				},
			},
		}
	} else {
		volumes = []corev1.Volume{
			{
				Name: PVCVolumeName,
				VolumeSource: corev1.VolumeSource{
					EmptyDir: &corev1.EmptyDirVolumeSource{},
				},
			},
		}
	}

	// Content source: either git clone or ConfigMap copy
	// contentKey tracks the notebook filename when content is specified (non-empty)
	var contentKey string
	if notebook.Spec.Content != nil && *notebook.Spec.Content != "" {
		// Content mode: mount ConfigMap and copy to notebook dir
		contentKey = DetectContentKey(*notebook.Spec.Content)
		volumes = append(volumes, corev1.Volume{
			Name: ConfigMapVolumeName,
			VolumeSource: corev1.VolumeSource{
				ConfigMap: &corev1.ConfigMapVolumeSource{
					LocalObjectReference: corev1.LocalObjectReference{
						Name: ConfigMapName(notebook.Name),
					},
				},
			},
		})
		initContainers = []corev1.Container{
			{
				Name:  "copy-content",
				Image: config.DefaultInitImage,
				Command: []string{"sh", "-c", fmt.Sprintf(
					"cp /content/%s %s/%s",
					ContentKey,
					NotebookDir,
					contentKey,
				)},
				VolumeMounts: []corev1.VolumeMount{
					{Name: PVCVolumeName, MountPath: NotebookDir},
					{Name: ConfigMapVolumeName, MountPath: "/content", ReadOnly: true},
				},
			},
		}
	} else if notebook.Spec.Source != "" {
		// Source mode: git clone (only if source URL provided)
		initContainers = []corev1.Container{
			{
				Name:  "git-clone",
				Image: config.GitImage,
				Command: []string{"sh", "-c", fmt.Sprintf(
					"if [ -d %s/.git ]; then echo 'Repository already exists, skipping clone'; else git clone --depth 1 %s %s; fi",
					NotebookDir,
					notebook.Spec.Source,
					NotebookDir,
				)},
				VolumeMounts: []corev1.VolumeMount{
					{Name: PVCVolumeName, MountPath: NotebookDir},
				},
			},
		}
	}
	// No init container for empty content + no source (plugin syncs via kubectl cp)

	// Add venv setup init container
	initContainers = append(initContainers, corev1.Container{
		Name:  "setup-venv",
		Image: notebook.Spec.Image,
		Command: []string{"sh", "-c",
			"if [ ! -f /opt/venv/bin/python ]; then echo 'Creating venv...'; uv venv /opt/venv; fi",
		},
		VolumeMounts: []corev1.VolumeMount{
			{Name: "venv", MountPath: "/opt/venv"},
		},
	})

	// Add venv volume (emptyDir, shared between init and main container)
	volumes = append(volumes, corev1.Volume{
		Name: "venv",
		VolumeSource: corev1.VolumeSource{
			EmptyDir: &corev1.EmptyDirVolumeSource{},
		},
	})

	volumeMounts = []corev1.VolumeMount{
		{Name: PVCVolumeName, MountPath: NotebookDir},
		{Name: "venv", MountPath: "/opt/venv"},
	}

	// Determine mode: use spec.Mode or default to "edit"
	mode := DefaultMode
	if notebook.Spec.Mode != "" {
		mode = notebook.Spec.Mode
	}

	// Build marimo command args (will be passed to shell wrapper)
	marimoArgs := []string{
		mode,
		"--headless",
		"--host=0.0.0.0",
		fmt.Sprintf("--port=%d", notebook.Spec.Port),
	}

	// Auth configuration:
	// - auth nil: auto-generate token (secure by default, plugin fetches from logs)
	// - auth.password set: use secret file
	// - auth present but empty: explicit opt-in to --no-token
	if notebook.Spec.Auth != nil {
		if notebook.Spec.Auth.Password != nil {
			marimoArgs = append(marimoArgs, "--token-password-file", "/etc/marimo/password")
			volumes = append(volumes, corev1.Volume{
				Name: "auth-secret",
				VolumeSource: corev1.VolumeSource{
					Secret: &corev1.SecretVolumeSource{
						SecretName: notebook.Spec.Auth.Password.SecretKeyRef.Name,
						Items: []corev1.KeyToPath{
							{
								Key:  notebook.Spec.Auth.Password.SecretKeyRef.Key,
								Path: "password",
							},
						},
					},
				},
			})
			volumeMounts = append(volumeMounts, corev1.VolumeMount{
				Name:      "auth-secret",
				MountPath: "/etc/marimo",
				ReadOnly:  true,
			})
		} else {
			// auth block present but no password = opt-in to disable auth
			marimoArgs = append(marimoArgs, "--no-token")
		}
	}

	// Final argument: notebook path
	// - With content: specific file with --sandbox (e.g., /home/marimo/notebooks/notebook.py)
	// - Without content: directory mode (e.g., /home/marimo/notebooks)
	if contentKey != "" {
		marimoArgs = append(marimoArgs, "--sandbox", fmt.Sprintf("%s/%s", NotebookDir, contentKey))
	} else {
		marimoArgs = append(marimoArgs, NotebookDir)
	}

	// Build base environment variables
	baseEnv := []corev1.EnvVar{
		// UV/venv environment configuration
		{Name: "VIRTUAL_ENV", Value: "/opt/venv"},
		{Name: "UV_PROJECT_ENVIRONMENT", Value: "/opt/venv"},
		{Name: "UV", Value: "/usr/bin/uv"},
		{Name: "UV_SYSTEM_PYTHON", Value: "1"},
		// TODO: Update this
		{Name: "MODAL_TASK_ID", Value: "1"},
		{Name: "PYTHONPATH", Value: "/usr/local/lib/python3.13/site-packages/:/opt/venv/lib/python3.13/site-packages/"},
	}

	// Append user-provided env vars (allows overrides)
	containerEnv := append(baseEnv, notebook.Spec.Env...)

	// Expand mounts to sidecars and merge with explicit sidecars
	// (do this first so we can check for FUSE sidecars)
	allSidecars := expandMounts(notebook.Spec.Mounts)
	allSidecars = append(allSidecars, notebook.Spec.Sidecars...)

	// Check if any sidecar uses FUSE (privileged) - if so, marimo container needs
	// HostToContainer propagation
	hasFUSESidecar := false
	hasSSHFSSidecar := false
	for _, sidecar := range allSidecars {
		if sidecar.SecurityContext != nil && sidecar.SecurityContext.Privileged != nil &&
			*sidecar.SecurityContext.Privileged {
			hasFUSESidecar = true
		}
		if strings.HasPrefix(sidecar.Name, "sshfs-") {
			hasSSHFSSidecar = true
		}
	}

	// Add ssh-pubkey secret volume if any sshfs sidecar exists
	// The plugin creates this secret from the user's public key
	if hasSSHFSSidecar {
		volumes = append(volumes, corev1.Volume{
			Name: "ssh-pubkey",
			VolumeSource: corev1.VolumeSource{
				Secret: &corev1.SecretVolumeSource{
					SecretName: "ssh-pubkey",
				},
			},
		})
	}

	// If there are FUSE sidecars, update marimo's volume mount with HostToContainer propagation
	marimoVolumeMounts := volumeMounts
	if hasFUSESidecar {
		marimoVolumeMounts = make([]corev1.VolumeMount, len(volumeMounts))
		copy(marimoVolumeMounts, volumeMounts)
		hostToContainer := corev1.MountPropagationHostToContainer
		for i := range marimoVolumeMounts {
			if marimoVolumeMounts[i].Name == PVCVolumeName {
				marimoVolumeMounts[i].MountPropagation = &hostToContainer
			}
		}
	}

	// Build main containers list starting with marimo
	// Command and args are passed directly - no shell wrapper needed
	containers := []corev1.Container{
		{
			Name:       "marimo",
			Image:      notebook.Spec.Image,
			WorkingDir: NotebookDir,
			Command:    []string{"marimo"},
			Args:       marimoArgs,
			Env:        containerEnv,
			Ports: []corev1.ContainerPort{
				{
					Name:          "http",
					ContainerPort: notebook.Spec.Port,
					Protocol:      corev1.ProtocolTCP,
				},
			},
			VolumeMounts: marimoVolumeMounts,
			Resources:    buildResourceRequirements(notebook.Spec.Resources),
		},
	}

	// Add sidecar containers (they share the PVC volume)
	for _, sidecar := range allSidecars {
		container := buildSidecarContainer(sidecar, volumeMounts)
		containers = append(containers, container)
	}

	basePodSpec := corev1.PodSpec{
		InitContainers: initContainers,
		Containers:     containers,
		Volumes:        volumes,
	}

	// Apply podOverrides if specified
	if notebook.Spec.PodOverrides != nil {
		basePodSpec = applyPodOverrides(basePodSpec, *notebook.Spec.PodOverrides)
	}

	return &corev1.Pod{
		ObjectMeta: metav1.ObjectMeta{
			Name:      notebook.Name,
			Namespace: notebook.Namespace,
			Labels:    Labels(notebook),
		},
		Spec: basePodSpec,
	}
}

// buildSidecarContainer creates a container spec from a SidecarSpec.
// Sidecars share the PVC volume with the main marimo container.
// FUSE-based sidecars (with privileged security context) get Bidirectional mount propagation.
// SSHFS sidecars (name starts with "sshfs-") get the ssh-pubkey secret mounted.
func buildSidecarContainer(sidecar marimov1alpha1.SidecarSpec, volumeMounts []corev1.VolumeMount) corev1.Container {
	// Copy volume mounts so we can modify them for this container
	sidecarMounts := make([]corev1.VolumeMount, len(volumeMounts))
	copy(sidecarMounts, volumeMounts)

	// If this sidecar needs privileged access (FUSE), set Bidirectional mount propagation
	// so FUSE mounts inside the sidecar are visible to other containers
	if sidecar.SecurityContext != nil && sidecar.SecurityContext.Privileged != nil && *sidecar.SecurityContext.Privileged {
		bidirectional := corev1.MountPropagationBidirectional
		for i := range sidecarMounts {
			if sidecarMounts[i].Name == PVCVolumeName {
				sidecarMounts[i].MountPropagation = &bidirectional
			}
		}
	}

	// SSHFS sidecars need the ssh-pubkey secret for key-based auth
	// The linuxserver/openssh-server image reads PUBLIC_KEY_FILE from this path
	if strings.HasPrefix(sidecar.Name, "sshfs-") {
		sidecarMounts = append(sidecarMounts, corev1.VolumeMount{
			Name:      "ssh-pubkey",
			MountPath: "/config/ssh-pubkey",
			ReadOnly:  true,
		})
	}

	container := corev1.Container{
		Name:         sidecar.Name,
		Image:        sidecar.Image,
		Env:          sidecar.Env,
		Command:      sidecar.Command,
		Args:         sidecar.Args,
		VolumeMounts: sidecarMounts, // Share PVC volume (with propagation if FUSE)
	}

	// Add port if ExposePort is set
	if sidecar.ExposePort != nil {
		container.Ports = []corev1.ContainerPort{
			{
				Name:          sidecar.Name,
				ContainerPort: *sidecar.ExposePort,
				Protocol:      corev1.ProtocolTCP,
			},
		}
	}

	// Add resources if specified
	if sidecar.Resources != nil {
		container.Resources = *sidecar.Resources
	}

	// Add security context if specified (needed for FUSE-based mounts)
	if sidecar.SecurityContext != nil {
		container.SecurityContext = sidecar.SecurityContext
	}

	return container
}

// buildResourceRequirements converts ResourcesSpec to corev1.ResourceRequirements.
func buildResourceRequirements(spec *marimov1alpha1.ResourcesSpec) corev1.ResourceRequirements {
	if spec == nil {
		return corev1.ResourceRequirements{}
	}
	return corev1.ResourceRequirements{
		Requests: spec.Requests,
		Limits:   spec.Limits,
	}
}

// applyPodOverrides merges overrides into base using strategic merge patch.
func applyPodOverrides(base, overrides corev1.PodSpec) corev1.PodSpec {
	baseJSON, err := json.Marshal(base)
	if err != nil {
		return base
	}
	overridesJSON, err := json.Marshal(overrides)
	if err != nil {
		return base
	}

	patchMeta, err := strategicpatch.NewPatchMetaFromStruct(&corev1.PodSpec{})
	if err != nil {
		return base
	}

	merged, err := strategicpatch.StrategicMergePatchUsingLookupPatchMeta(
		baseJSON, overridesJSON, patchMeta)
	if err != nil {
		return base
	}

	var result corev1.PodSpec
	if err := json.Unmarshal(merged, &result); err != nil {
		return base
	}
	return result
}

// parseCWMountURI parses a cw:// URI for CoreWeave S3 mounts.
// Format: cw://bucket[/path][:mount_point]
// Returns: (bucket, subpath, mountPoint)
func parseCWMountURI(uri string) (bucket, subpath, mountPoint string) {
	trimmed := strings.TrimPrefix(uri, "cw://")

	// Check for custom mount point (last :/)
	lastColonIdx := strings.LastIndex(trimmed, ":/")
	if lastColonIdx > 0 {
		mountPoint = trimmed[lastColonIdx+1:]
		trimmed = trimmed[:lastColonIdx]
	}

	// Split bucket/path
	parts := strings.SplitN(trimmed, "/", 2)
	bucket = parts[0]
	if len(parts) > 1 {
		subpath = parts[1]
	}

	return bucket, subpath, mountPoint
}

// expandMounts converts mount URIs to sidecar specs.
// Supported schemes:
// - cw://bucket/path → CoreWeave S3 sidecar using s3fs
// - cw://bucket/path:/mount → CoreWeave S3 with custom mount point
//
// Note: sshfs:// and rsync:// mounts are handled by the kubectl-marimo plugin,
// not the operator. The plugin adds explicit sidecar specs to the CRD.
func expandMounts(mounts []string) []marimov1alpha1.SidecarSpec {
	var sidecars []marimov1alpha1.SidecarSpec

	for i, mount := range mounts {
		if strings.HasPrefix(mount, "cw://") {
			if sidecar := buildCWSidecar(mount, i); sidecar != nil {
				sidecars = append(sidecars, *sidecar)
			}
		}
		// sshfs:// and rsync:// are handled by plugin - ignore here
	}

	return sidecars
}

// CWCredentialsSecret is the name of the K8s secret containing S3 credentials.
// The kubectl-marimo plugin auto-creates this from ~/.s3cfg.
const CWCredentialsSecret = "cw-credentials"

// buildCWSidecar creates a sidecar spec for CoreWeave S3 mount using s3fs.
// URI format: cw://bucket[/path][:mount]
// Credentials from cw-credentials secret (auto-created by kubectl-marimo plugin).
// Endpoint from S3_ENDPOINT env var (default: https://cwobject.com).
func buildCWSidecar(uri string, index int) *marimov1alpha1.SidecarSpec {
	bucket, subpath, customMount := parseCWMountURI(uri)
	if bucket == "" {
		return nil
	}

	mountName := fmt.Sprintf("cw-%d", index)

	localMountPoint := customMount
	if localMountPoint == "" {
		localMountPoint = fmt.Sprintf("%s/mounts/%s", NotebookDir, mountName)
	}

	// Build bucket:/path string for s3fs
	remotePath := bucket
	if subpath != "" {
		remotePath = bucket + ":/" + subpath
	}

	return &marimov1alpha1.SidecarSpec{
		Name:    mountName,
		Image:   config.S3FSImage,
		Command: []string{"sh", "-c"},
		Args: []string{
			fmt.Sprintf(
				`mkdir -p %s && `+
					`echo "$AWS_ACCESS_KEY_ID:$AWS_SECRET_ACCESS_KEY" > /etc/passwd-s3fs && `+
					`chmod 600 /etc/passwd-s3fs && `+
					`s3fs %s %s `+
					`-o passwd_file=/etc/passwd-s3fs `+
					`-o url=${S3_ENDPOINT:-https://cwobject.com} `+
					`-o allow_other `+
					`-o umask=0000 `+
					`-f`,
				localMountPoint,
				remotePath,
				localMountPoint,
			),
		},
		Env: []corev1.EnvVar{
			{
				Name: "AWS_ACCESS_KEY_ID",
				ValueFrom: &corev1.EnvVarSource{
					SecretKeyRef: &corev1.SecretKeySelector{
						LocalObjectReference: corev1.LocalObjectReference{Name: CWCredentialsSecret},
						Key:                  "AWS_ACCESS_KEY_ID",
					},
				},
			},
			{
				Name: "AWS_SECRET_ACCESS_KEY",
				ValueFrom: &corev1.EnvVarSource{
					SecretKeyRef: &corev1.SecretKeySelector{
						LocalObjectReference: corev1.LocalObjectReference{Name: CWCredentialsSecret},
						Key:                  "AWS_SECRET_ACCESS_KEY",
					},
				},
			},
		},
		// FUSE requires privileged access to /dev/fuse
		SecurityContext: &corev1.SecurityContext{
			Privileged: ptrBool(true),
		},
	}
}

// ptrBool returns a pointer to a bool value.
func ptrBool(b bool) *bool {
	return &b
}

// ptrString returns a pointer to a string value.
func ptrString(s string) *string {
	return &s
}
