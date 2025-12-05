package resources

import (
	"encoding/json"
	"fmt"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/strategicpatch"

	marimov1alpha1 "github.com/marimo-team/marimo-operator/api/v1alpha1"
)

const (
	// DefaultInitImage is the default image for init containers.
	DefaultInitImage = "busybox:1.36"
	// NotebookDir is the directory where notebooks are stored.
	NotebookDir = "/home/marimo/notebooks"
)

// BuildPod creates a Pod spec for a MarimoNotebook.
// For this base implementation, content is cloned from spec.Source (git URL).
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

	// Init containers: git-clone and venv setup
	initContainers = []corev1.Container{
		{
			Name:  "git-clone",
			Image: "alpine/git:latest",
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
		{
			Name:  "setup-venv",
			Image: notebook.Spec.Image,
			Command: []string{"sh", "-c",
				"if [ ! -f /opt/venv/bin/python ]; then echo 'Creating venv...'; uv venv /opt/venv; fi",
			},
			VolumeMounts: []corev1.VolumeMount{
				{Name: "venv", MountPath: "/opt/venv"},
			},
		},
	}

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

	// Build marimo command args (will be passed to shell wrapper)
	marimoArgs := []string{
		"edit",
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

	// Final argument: notebook directory
	marimoArgs = append(marimoArgs, NotebookDir)

	// Build main containers list starting with marimo
	// Command and args are passed directly - no shell wrapper needed
	containers := []corev1.Container{
		{
			Name:       "marimo",
			Image:      notebook.Spec.Image,
			WorkingDir: NotebookDir,
			Command:    []string{"marimo"},
			Args:       marimoArgs,
			Env: []corev1.EnvVar{
				// UV/venv environment configuration
				{Name: "VIRTUAL_ENV", Value: "/opt/venv"},
				{Name: "UV_PROJECT_ENVIRONMENT", Value: "/opt/venv"},
				{Name: "UV", Value: "/usr/bin/uv"},
				{Name: "UV_SYSTEM_PYTHON", Value: "1"},
				// TODO: Update this
				{Name: "MODAL_TASK_ID", Value: "1"},
				{Name: "PYTHONPATH", Value: "/usr/local/lib/python3.13/site-packages/:/opt/venv/lib/python3.13/site-packages/"},
			},
			Ports: []corev1.ContainerPort{
				{
					Name:          "http",
					ContainerPort: notebook.Spec.Port,
					Protocol:      corev1.ProtocolTCP,
				},
			},
			VolumeMounts: volumeMounts,
			Resources:    buildResourceRequirements(notebook.Spec.Resources),
		},
	}

	// Add sidecar containers (they share the PVC volume)
	for _, sidecar := range notebook.Spec.Sidecars {
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
func buildSidecarContainer(sidecar marimov1alpha1.SidecarSpec, volumeMounts []corev1.VolumeMount) corev1.Container {
	container := corev1.Container{
		Name:         sidecar.Name,
		Image:        sidecar.Image,
		Env:          sidecar.Env,
		Command:      sidecar.Command,
		Args:         sidecar.Args,
		VolumeMounts: volumeMounts, // Share PVC volume
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
