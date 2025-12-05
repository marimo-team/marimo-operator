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

	// Always use emptyDir for now (PVC support added in later commit)
	volumes = []corev1.Volume{
		{
			Name: "notebook-data",
			VolumeSource: corev1.VolumeSource{
				EmptyDir: &corev1.EmptyDirVolumeSource{},
			},
		},
	}

	// Init container clones from git source
	initContainers = []corev1.Container{
		{
			Name:  "git-clone",
			Image: "alpine/git:latest",
			Command: []string{"sh", "-c", fmt.Sprintf(
				"git clone --depth 1 %s %s",
				notebook.Spec.Source,
				NotebookDir,
			)},
			VolumeMounts: []corev1.VolumeMount{
				{Name: "notebook-data", MountPath: NotebookDir},
			},
		},
	}

	volumeMounts = []corev1.VolumeMount{
		{Name: "notebook-data", MountPath: NotebookDir},
	}

	// Build marimo command args
	args := []string{
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
			args = append(args, "--token-password-file", "/etc/marimo/password")
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
			args = append(args, "--no-token")
		}
	}

	// Final argument: notebook directory
	args = append(args, NotebookDir)

	basePodSpec := corev1.PodSpec{
		InitContainers: initContainers,
		Containers: []corev1.Container{
			{
				Name:    "marimo",
				Image:   notebook.Spec.Image,
				Command: []string{"marimo"},
				Args:    args,
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
		},
		Volumes: volumes,
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
