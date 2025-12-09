package resources

import (
	"strings"
	"testing"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	marimov1alpha1 "github.com/marimo-team/marimo-operator/api/v1alpha1"
)

func TestBuildPod_BasicConfig(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
		},
	}

	pod := BuildPod(notebook)

	// Check metadata
	if pod.Name != "test-notebook" {
		t.Errorf("expected pod name 'test-notebook', got '%s'", pod.Name)
	}
	if pod.Namespace != "default" {
		t.Errorf("expected namespace 'default', got '%s'", pod.Namespace)
	}

	// Check labels
	if pod.Labels["app.kubernetes.io/name"] != "marimo" {
		t.Errorf("expected label app.kubernetes.io/name='marimo', got '%s'", pod.Labels["app.kubernetes.io/name"])
	}
	if pod.Labels["app.kubernetes.io/instance"] != "test-notebook" {
		t.Errorf("expected label app.kubernetes.io/instance='test-notebook', got '%s'", pod.Labels["app.kubernetes.io/instance"])
	}

	// Check main container
	if len(pod.Spec.Containers) != 1 {
		t.Fatalf("expected 1 container, got %d", len(pod.Spec.Containers))
	}
	container := pod.Spec.Containers[0]
	if container.Name != "marimo" {
		t.Errorf("expected container name 'marimo', got '%s'", container.Name)
	}
	if container.Image != "ghcr.io/marimo-team/marimo:latest" {
		t.Errorf("expected image 'ghcr.io/marimo-team/marimo:latest', got '%s'", container.Image)
	}
	// Command should run marimo directly (no shell wrapper)
	if container.Command[0] != "marimo" {
		t.Errorf("expected command 'marimo', got '%s'", container.Command[0])
	}
	// Args should contain the marimo arguments
	if len(container.Args) == 0 {
		t.Error("expected marimo args to be set")
	}

	// Check working directory
	if container.WorkingDir != NotebookDir {
		t.Errorf("expected working dir '%s', got '%s'", NotebookDir, container.WorkingDir)
	}

	// Check port
	if len(container.Ports) != 1 || container.Ports[0].ContainerPort != 2718 {
		t.Errorf("expected port 2718, got %v", container.Ports)
	}

	// Check init containers (git-clone and setup-venv)
	if len(pod.Spec.InitContainers) != 2 {
		t.Fatalf("expected 2 init containers, got %d", len(pod.Spec.InitContainers))
	}
	gitClone := pod.Spec.InitContainers[0]
	if gitClone.Name != "git-clone" {
		t.Errorf("expected first init container name 'git-clone', got '%s'", gitClone.Name)
	}
	if gitClone.Image != "alpine/git:latest" {
		t.Errorf("expected init image 'alpine/git:latest', got '%s'", gitClone.Image)
	}
	setupVenv := pod.Spec.InitContainers[1]
	if setupVenv.Name != "setup-venv" {
		t.Errorf("expected second init container name 'setup-venv', got '%s'", setupVenv.Name)
	}

	// Check volume mounts
	if len(container.VolumeMounts) == 0 {
		t.Error("expected at least one volume mount")
	}
	foundNotebookMount := false
	for _, vm := range container.VolumeMounts {
		if vm.MountPath == NotebookDir {
			foundNotebookMount = true
			break
		}
	}
	if !foundNotebookMount {
		t.Errorf("expected volume mount at %s", NotebookDir)
	}
}

func TestBuildPod_AuthNil_NoTokenFlag(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Auth:   nil, // Auto-generate token (no --no-token flag)
		},
	}

	pod := BuildPod(notebook)
	container := pod.Spec.Containers[0]

	// Auth nil means auto-generate token (secure by default)
	// Args should NOT have --no-token
	for _, arg := range container.Args {
		if arg == "--no-token" {
			t.Error("auth=nil should not have --no-token flag (secure by default)")
		}
	}
}

func TestBuildPod_AuthEmptyBlock_NoTokenFlag(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Auth:   &marimov1alpha1.AuthSpec{}, // Empty auth = opt-in to no token
		},
	}

	pod := BuildPod(notebook)
	container := pod.Spec.Containers[0]

	// Empty auth block means explicit opt-in to --no-token
	foundNoToken := false
	for _, arg := range container.Args {
		if arg == "--no-token" {
			foundNoToken = true
			break
		}
	}
	if !foundNoToken {
		t.Error("empty auth block should have --no-token flag")
	}
}

func TestBuildPod_AuthWithPassword(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Auth: &marimov1alpha1.AuthSpec{
				Password: &marimov1alpha1.SecretKeySelector{
					SecretKeyRef: corev1.SecretKeySelector{
						LocalObjectReference: corev1.LocalObjectReference{
							Name: "marimo-secret",
						},
						Key: "password",
					},
				},
			},
		},
	}

	pod := BuildPod(notebook)
	container := pod.Spec.Containers[0]

	// Args should have --token-password-file
	foundPasswordFile := false
	for i, arg := range container.Args {
		if arg == "--token-password-file" && i+1 < len(container.Args) {
			if container.Args[i+1] == "/etc/marimo/password" {
				foundPasswordFile = true
			}
			break
		}
	}
	if !foundPasswordFile {
		t.Error("auth with password should have --token-password-file /etc/marimo/password")
	}

	// Should have auth-secret volume
	foundSecretVolume := false
	for _, vol := range pod.Spec.Volumes {
		if vol.Name == "auth-secret" && vol.Secret != nil {
			if vol.Secret.SecretName == "marimo-secret" {
				foundSecretVolume = true
			}
			break
		}
	}
	if !foundSecretVolume {
		t.Error("auth with password should have auth-secret volume")
	}

	// Should have volume mount
	foundSecretMount := false
	for _, vm := range container.VolumeMounts {
		if vm.Name == "auth-secret" && vm.MountPath == "/etc/marimo" {
			foundSecretMount = true
			break
		}
	}
	if !foundSecretMount {
		t.Error("auth with password should have auth-secret volume mount")
	}
}

func TestBuildPod_Resources(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Resources: &marimov1alpha1.ResourcesSpec{
				Requests: corev1.ResourceList{
					corev1.ResourceCPU:    resource.MustParse("100m"),
					corev1.ResourceMemory: resource.MustParse("256Mi"),
				},
				Limits: corev1.ResourceList{
					corev1.ResourceCPU:    resource.MustParse("1"),
					corev1.ResourceMemory: resource.MustParse("1Gi"),
				},
			},
		},
	}

	pod := BuildPod(notebook)
	container := pod.Spec.Containers[0]

	// Check requests
	if cpu := container.Resources.Requests.Cpu(); cpu.String() != "100m" {
		t.Errorf("expected CPU request '100m', got '%s'", cpu.String())
	}
	if mem := container.Resources.Requests.Memory(); mem.String() != "256Mi" {
		t.Errorf("expected memory request '256Mi', got '%s'", mem.String())
	}

	// Check limits
	if cpu := container.Resources.Limits.Cpu(); cpu.String() != "1" {
		t.Errorf("expected CPU limit '1', got '%s'", cpu.String())
	}
	if mem := container.Resources.Limits.Memory(); mem.String() != "1Gi" {
		t.Errorf("expected memory limit '1Gi', got '%s'", mem.String())
	}
}

func TestBuildPod_PodOverrides(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			PodOverrides: &corev1.PodSpec{
				NodeSelector: map[string]string{
					"gpu": "true",
				},
			},
		},
	}

	pod := BuildPod(notebook)

	// Check that nodeSelector was applied
	if pod.Spec.NodeSelector == nil {
		t.Fatal("expected nodeSelector to be set")
	}
	if pod.Spec.NodeSelector["gpu"] != "true" {
		t.Errorf("expected nodeSelector gpu='true', got '%s'", pod.Spec.NodeSelector["gpu"])
	}
}

func TestBuildPod_CustomPort(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   8080,
			Source: "https://github.com/marimo-team/marimo.git",
		},
	}

	pod := BuildPod(notebook)
	container := pod.Spec.Containers[0]

	// Check port
	if container.Ports[0].ContainerPort != 8080 {
		t.Errorf("expected port 8080, got %d", container.Ports[0].ContainerPort)
	}

	// Check args contains correct port
	foundPortArg := false
	for _, arg := range container.Args {
		if arg == "--port=8080" {
			foundPortArg = true
			break
		}
	}
	if !foundPortArg {
		t.Error("expected --port=8080 in args")
	}
}

func TestBuildResourceRequirements_Nil(t *testing.T) {
	result := buildResourceRequirements(nil)
	if result.Requests != nil || result.Limits != nil {
		t.Error("expected empty ResourceRequirements for nil input")
	}
}

func TestApplyPodOverrides_MergeContainerResources(t *testing.T) {
	base := corev1.PodSpec{
		Containers: []corev1.Container{
			{
				Name:  "marimo",
				Image: "marimo:latest",
			},
		},
	}

	overrides := corev1.PodSpec{
		Containers: []corev1.Container{
			{
				Name: "marimo",
				Resources: corev1.ResourceRequirements{
					Limits: corev1.ResourceList{
						corev1.ResourceMemory: resource.MustParse("2Gi"),
					},
				},
			},
		},
	}

	result := applyPodOverrides(base, overrides)

	// Container should still exist with merged resources
	if len(result.Containers) == 0 {
		t.Fatal("expected at least one container")
	}
	if result.Containers[0].Name != "marimo" {
		t.Errorf("expected container name 'marimo', got '%s'", result.Containers[0].Name)
	}
	// Strategic merge should merge container by name
	if mem := result.Containers[0].Resources.Limits.Memory(); mem.String() != "2Gi" {
		t.Errorf("expected memory limit '2Gi', got '%s'", mem.String())
	}
}

func TestBuildPod_WithStorage_UsesPVC(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Storage: &marimov1alpha1.StorageSpec{
				Size: "5Gi",
			},
		},
	}

	pod := BuildPod(notebook)

	// Check that volume uses PVC
	var foundPVCVolume bool
	for _, vol := range pod.Spec.Volumes {
		if vol.Name == PVCVolumeName {
			if vol.PersistentVolumeClaim == nil {
				t.Error("expected PVC volume source when storage is configured")
			} else if vol.PersistentVolumeClaim.ClaimName != "test-notebook" {
				t.Errorf("expected PVC claim name 'test-notebook', got '%s'", vol.PersistentVolumeClaim.ClaimName)
			}
			foundPVCVolume = true
			break
		}
	}
	if !foundPVCVolume {
		t.Error("expected to find notebook-data volume")
	}

	// Check that main container mounts the volume
	container := pod.Spec.Containers[0]
	var foundMount bool
	for _, vm := range container.VolumeMounts {
		if vm.Name == PVCVolumeName && vm.MountPath == NotebookDir {
			foundMount = true
			break
		}
	}
	if !foundMount {
		t.Errorf("expected volume mount at %s", NotebookDir)
	}
}

func TestBuildPod_WithoutStorage_UsesEmptyDir(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			// No storage configured
		},
	}

	pod := BuildPod(notebook)

	// Check that volume uses emptyDir
	var foundEmptyDirVolume bool
	for _, vol := range pod.Spec.Volumes {
		if vol.Name == PVCVolumeName {
			if vol.EmptyDir == nil {
				t.Error("expected emptyDir volume source when storage is not configured")
			}
			foundEmptyDirVolume = true
			break
		}
	}
	if !foundEmptyDirVolume {
		t.Error("expected to find notebook-data volume with emptyDir")
	}
}

func TestBuildPod_InitContainer_IdempotentClone(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Storage: &marimov1alpha1.StorageSpec{
				Size: "1Gi",
			},
		},
	}

	pod := BuildPod(notebook)

	// Should have 2 init containers: git-clone and setup-venv
	if len(pod.Spec.InitContainers) != 2 {
		t.Fatalf("expected 2 init containers, got %d", len(pod.Spec.InitContainers))
	}

	// Check git-clone init container
	gitClone := pod.Spec.InitContainers[0]
	if gitClone.Name != "git-clone" {
		t.Errorf("expected first init container 'git-clone', got '%s'", gitClone.Name)
	}
	if len(gitClone.Command) < 3 {
		t.Fatal("expected git-clone command with shell script")
	}
	script := gitClone.Command[2]
	if !contains(script, "if [ -d") || !contains(script, ".git ]") {
		t.Error("git-clone should check for existing .git directory")
	}
	if !contains(script, "skipping clone") {
		t.Error("git-clone should skip clone if repo exists")
	}
	if !contains(script, "git clone") {
		t.Error("git-clone should clone if repo doesn't exist")
	}

	// Check setup-venv init container
	setupVenv := pod.Spec.InitContainers[1]
	if setupVenv.Name != "setup-venv" {
		t.Errorf("expected second init container 'setup-venv', got '%s'", setupVenv.Name)
	}
	if setupVenv.Image != "ghcr.io/marimo-team/marimo:latest" {
		t.Errorf("setup-venv should use marimo image, got '%s'", setupVenv.Image)
	}
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > 0 && containsHelper(s, substr))
}

func containsHelper(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

func TestBuildPod_WithSidecar(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Storage: &marimov1alpha1.StorageSpec{
				Size: "5Gi",
			},
			Sidecars: []marimov1alpha1.SidecarSpec{
				{
					Name:  "sshd",
					Image: "linuxserver/openssh-server:latest",
				},
			},
		},
	}

	pod := BuildPod(notebook)

	// Should have 2 containers: marimo + sidecar
	if len(pod.Spec.Containers) != 2 {
		t.Fatalf("expected 2 containers, got %d", len(pod.Spec.Containers))
	}

	// Check marimo container is first
	if pod.Spec.Containers[0].Name != "marimo" {
		t.Errorf("expected first container to be 'marimo', got '%s'", pod.Spec.Containers[0].Name)
	}

	// Check sidecar container
	sidecar := pod.Spec.Containers[1]
	if sidecar.Name != "sshd" {
		t.Errorf("expected sidecar name 'sshd', got '%s'", sidecar.Name)
	}
	if sidecar.Image != "linuxserver/openssh-server:latest" {
		t.Errorf("expected sidecar image 'linuxserver/openssh-server:latest', got '%s'", sidecar.Image)
	}

	// Sidecar should share the PVC volume mount
	var foundMount bool
	for _, vm := range sidecar.VolumeMounts {
		if vm.Name == PVCVolumeName && vm.MountPath == NotebookDir {
			foundMount = true
			break
		}
	}
	if !foundMount {
		t.Errorf("sidecar should share PVC volume mount at %s", NotebookDir)
	}
}

func TestBuildPod_SidecarWithExposePort(t *testing.T) {
	port := int32(22)
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Storage: &marimov1alpha1.StorageSpec{
				Size: "5Gi",
			},
			Sidecars: []marimov1alpha1.SidecarSpec{
				{
					Name:       "sshd",
					Image:      "linuxserver/openssh-server:latest",
					ExposePort: &port,
				},
			},
		},
	}

	pod := BuildPod(notebook)

	sidecar := pod.Spec.Containers[1]

	// Sidecar should have port exposed
	if len(sidecar.Ports) != 1 {
		t.Fatalf("expected 1 port on sidecar, got %d", len(sidecar.Ports))
	}
	if sidecar.Ports[0].ContainerPort != 22 {
		t.Errorf("expected sidecar port 22, got %d", sidecar.Ports[0].ContainerPort)
	}
	if sidecar.Ports[0].Name != "sshd" {
		t.Errorf("expected port name 'sshd', got '%s'", sidecar.Ports[0].Name)
	}
}

func TestBuildPod_SidecarWithEnvCommandArgs(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Storage: &marimov1alpha1.StorageSpec{
				Size: "5Gi",
			},
			Sidecars: []marimov1alpha1.SidecarSpec{
				{
					Name:  "git-sync",
					Image: "registry.k8s.io/git-sync/git-sync:v4.2.1",
					Env: []corev1.EnvVar{
						{Name: "GITSYNC_REPO", Value: "https://github.com/example/repo.git"},
						{Name: "GITSYNC_PERIOD", Value: "30s"},
					},
					Command: []string{"/git-sync"},
					Args:    []string{"--one-time"},
				},
			},
		},
	}

	pod := BuildPod(notebook)

	sidecar := pod.Spec.Containers[1]

	// Check env vars
	if len(sidecar.Env) != 2 {
		t.Fatalf("expected 2 env vars, got %d", len(sidecar.Env))
	}
	if sidecar.Env[0].Name != "GITSYNC_REPO" {
		t.Errorf("expected first env var name 'GITSYNC_REPO', got '%s'", sidecar.Env[0].Name)
	}
	if sidecar.Env[1].Value != "30s" {
		t.Errorf("expected GITSYNC_PERIOD='30s', got '%s'", sidecar.Env[1].Value)
	}

	// Check command and args
	if len(sidecar.Command) != 1 || sidecar.Command[0] != "/git-sync" {
		t.Errorf("expected command '/git-sync', got %v", sidecar.Command)
	}
	if len(sidecar.Args) != 1 || sidecar.Args[0] != "--one-time" {
		t.Errorf("expected args '--one-time', got %v", sidecar.Args)
	}
}

func TestBuildPod_SidecarWithResources(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Storage: &marimov1alpha1.StorageSpec{
				Size: "5Gi",
			},
			Sidecars: []marimov1alpha1.SidecarSpec{
				{
					Name:  "helper",
					Image: "busybox:latest",
					Resources: &corev1.ResourceRequirements{
						Requests: corev1.ResourceList{
							corev1.ResourceCPU:    resource.MustParse("50m"),
							corev1.ResourceMemory: resource.MustParse("64Mi"),
						},
						Limits: corev1.ResourceList{
							corev1.ResourceCPU:    resource.MustParse("100m"),
							corev1.ResourceMemory: resource.MustParse("128Mi"),
						},
					},
				},
			},
		},
	}

	pod := BuildPod(notebook)

	sidecar := pod.Spec.Containers[1]

	// Check resources
	if cpu := sidecar.Resources.Requests.Cpu(); cpu.String() != "50m" {
		t.Errorf("expected CPU request '50m', got '%s'", cpu.String())
	}
	if mem := sidecar.Resources.Requests.Memory(); mem.String() != "64Mi" {
		t.Errorf("expected memory request '64Mi', got '%s'", mem.String())
	}
	if cpu := sidecar.Resources.Limits.Cpu(); cpu.String() != "100m" {
		t.Errorf("expected CPU limit '100m', got '%s'", cpu.String())
	}
	if mem := sidecar.Resources.Limits.Memory(); mem.String() != "128Mi" {
		t.Errorf("expected memory limit '128Mi', got '%s'", mem.String())
	}
}

func TestBuildPod_MultipleSidecars(t *testing.T) {
	sshPort := int32(22)
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Storage: &marimov1alpha1.StorageSpec{
				Size: "5Gi",
			},
			Sidecars: []marimov1alpha1.SidecarSpec{
				{
					Name:       "sshd",
					Image:      "linuxserver/openssh-server:latest",
					ExposePort: &sshPort,
				},
				{
					Name:  "git-sync",
					Image: "registry.k8s.io/git-sync/git-sync:v4.2.1",
				},
			},
		},
	}

	pod := BuildPod(notebook)

	// Should have 3 containers: marimo + 2 sidecars
	if len(pod.Spec.Containers) != 3 {
		t.Fatalf("expected 3 containers, got %d", len(pod.Spec.Containers))
	}

	// Check container order
	if pod.Spec.Containers[0].Name != "marimo" {
		t.Errorf("expected first container 'marimo', got '%s'", pod.Spec.Containers[0].Name)
	}
	if pod.Spec.Containers[1].Name != "sshd" {
		t.Errorf("expected second container 'sshd', got '%s'", pod.Spec.Containers[1].Name)
	}
	if pod.Spec.Containers[2].Name != "git-sync" {
		t.Errorf("expected third container 'git-sync', got '%s'", pod.Spec.Containers[2].Name)
	}

	// All sidecars should share the volume
	for i := 1; i < len(pod.Spec.Containers); i++ {
		sidecar := pod.Spec.Containers[i]
		var foundMount bool
		for _, vm := range sidecar.VolumeMounts {
			if vm.Name == PVCVolumeName {
				foundMount = true
				break
			}
		}
		if !foundMount {
			t.Errorf("sidecar %s should have PVC volume mount", sidecar.Name)
		}
	}
}

func TestBuildPod_WithContent(t *testing.T) {
	content := `import marimo as mo
app = mo.App()

@app.cell
def hello():
    return mo.md("# Hello World")
`
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:   "ghcr.io/marimo-team/marimo:latest",
			Port:    2718,
			Content: &content,
		},
	}

	pod := BuildPod(notebook)

	// Should have 2 init containers: copy-content and setup-venv (not git-clone)
	if len(pod.Spec.InitContainers) != 2 {
		t.Fatalf("expected 2 init containers, got %d", len(pod.Spec.InitContainers))
	}
	if pod.Spec.InitContainers[0].Name != "copy-content" {
		t.Errorf("expected first init container 'copy-content', got '%s'", pod.Spec.InitContainers[0].Name)
	}
	if pod.Spec.InitContainers[1].Name != "setup-venv" {
		t.Errorf("expected second init container 'setup-venv', got '%s'", pod.Spec.InitContainers[1].Name)
	}

	// Check that ConfigMap volume is present
	var foundConfigMapVolume bool
	for _, vol := range pod.Spec.Volumes {
		if vol.Name == ConfigMapVolumeName {
			if vol.ConfigMap == nil {
				t.Error("expected ConfigMap volume source")
			} else if vol.ConfigMap.Name != "test-notebook-content" {
				t.Errorf("expected ConfigMap name 'test-notebook-content', got '%s'", vol.ConfigMap.Name)
			}
			foundConfigMapVolume = true
			break
		}
	}
	if !foundConfigMapVolume {
		t.Error("expected to find ConfigMap volume")
	}

	// Check copy-content init container mounts ConfigMap
	copyContent := pod.Spec.InitContainers[0]
	var foundConfigMapMount bool
	for _, vm := range copyContent.VolumeMounts {
		if vm.Name == ConfigMapVolumeName && vm.MountPath == "/content" {
			foundConfigMapMount = true
			break
		}
	}
	if !foundConfigMapMount {
		t.Error("expected copy-content to mount ConfigMap at /content")
	}
}

func TestBuildSidecarContainer(t *testing.T) {
	port := int32(8080)
	sidecar := marimov1alpha1.SidecarSpec{
		Name:       "test-sidecar",
		Image:      "test-image:latest",
		ExposePort: &port,
		Env: []corev1.EnvVar{
			{Name: "FOO", Value: "bar"},
		},
		Command: []string{"/bin/sh"},
		Args:    []string{"-c", "echo hello"},
		Resources: &corev1.ResourceRequirements{
			Limits: corev1.ResourceList{
				corev1.ResourceMemory: resource.MustParse("256Mi"),
			},
		},
	}

	volumeMounts := []corev1.VolumeMount{
		{Name: "data", MountPath: "/data"},
	}

	container := buildSidecarContainer(sidecar, volumeMounts)

	if container.Name != "test-sidecar" {
		t.Errorf("expected name 'test-sidecar', got '%s'", container.Name)
	}
	if container.Image != "test-image:latest" {
		t.Errorf("expected image 'test-image:latest', got '%s'", container.Image)
	}
	if len(container.Ports) != 1 || container.Ports[0].ContainerPort != 8080 {
		t.Errorf("expected port 8080, got %v", container.Ports)
	}
	if len(container.Env) != 1 || container.Env[0].Value != "bar" {
		t.Errorf("expected env FOO=bar, got %v", container.Env)
	}
	if len(container.Command) != 1 || container.Command[0] != "/bin/sh" {
		t.Errorf("expected command '/bin/sh', got %v", container.Command)
	}
	if len(container.Args) != 2 || container.Args[1] != "echo hello" {
		t.Errorf("expected args '-c echo hello', got %v", container.Args)
	}
	if mem := container.Resources.Limits.Memory(); mem.String() != "256Mi" {
		t.Errorf("expected memory limit '256Mi', got '%s'", mem.String())
	}
	if len(container.VolumeMounts) != 1 || container.VolumeMounts[0].MountPath != "/data" {
		t.Errorf("expected volume mount at /data, got %v", container.VolumeMounts)
	}
}

func TestBuildPod_ModeDefault(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			// Mode not set, should default to "edit"
		},
	}

	pod := BuildPod(notebook)
	container := pod.Spec.Containers[0]

	// First arg should be "edit" (default mode)
	if len(container.Args) == 0 {
		t.Fatal("expected marimo args")
	}
	if container.Args[0] != "edit" {
		t.Errorf("expected default mode 'edit', got '%s'", container.Args[0])
	}
}

func TestBuildPod_ModeRun(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Mode:   "run",
		},
	}

	pod := BuildPod(notebook)
	container := pod.Spec.Containers[0]

	// First arg should be "run"
	if len(container.Args) == 0 {
		t.Fatal("expected marimo args")
	}
	if container.Args[0] != "run" {
		t.Errorf("expected mode 'run', got '%s'", container.Args[0])
	}
}

func TestBuildPod_ModeEdit(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Mode:   "edit",
		},
	}

	pod := BuildPod(notebook)
	container := pod.Spec.Containers[0]

	// First arg should be "edit"
	if len(container.Args) == 0 {
		t.Fatal("expected marimo args")
	}
	if container.Args[0] != "edit" {
		t.Errorf("expected mode 'edit', got '%s'", container.Args[0])
	}
}

func TestBuildPod_EnvVars(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Env: []corev1.EnvVar{
				{Name: "DEBUG", Value: "true"},
				{Name: "API_KEY", ValueFrom: &corev1.EnvVarSource{
					SecretKeyRef: &corev1.SecretKeySelector{
						LocalObjectReference: corev1.LocalObjectReference{
							Name: "my-secret",
						},
						Key: "api-key",
					},
				}},
			},
		},
	}

	pod := BuildPod(notebook)
	container := pod.Spec.Containers[0]

	// Should have base env vars + user env vars
	if len(container.Env) < 8 { // 6 base + 2 user
		t.Fatalf("expected at least 8 env vars, got %d", len(container.Env))
	}

	// Check base env vars are present
	foundVirtualEnv := false
	for _, env := range container.Env {
		if env.Name == "VIRTUAL_ENV" && env.Value == "/opt/venv" {
			foundVirtualEnv = true
			break
		}
	}
	if !foundVirtualEnv {
		t.Error("expected base env var VIRTUAL_ENV to be present")
	}

	// Check user env vars are appended
	foundDebug := false
	foundAPIKey := false
	for _, env := range container.Env {
		if env.Name == "DEBUG" && env.Value == "true" {
			foundDebug = true
		}
		if env.Name == "API_KEY" && env.ValueFrom != nil && env.ValueFrom.SecretKeyRef != nil {
			if env.ValueFrom.SecretKeyRef.Name == "my-secret" && env.ValueFrom.SecretKeyRef.Key == "api-key" {
				foundAPIKey = true
			}
		}
	}
	if !foundDebug {
		t.Error("expected user env var DEBUG=true to be present")
	}
	if !foundAPIKey {
		t.Error("expected user env var API_KEY from secret to be present")
	}
}

func TestBuildPod_EnvVarsEmpty(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			// No Env specified
		},
	}

	pod := BuildPod(notebook)
	container := pod.Spec.Containers[0]

	// Should have exactly 6 base env vars
	if len(container.Env) != 6 {
		t.Errorf("expected 6 base env vars, got %d", len(container.Env))
	}
}

func TestExpandMounts_SSHFS(t *testing.T) {
	mounts := []string{
		"sshfs://user@host.example.com:/data/notebooks",
	}

	sidecars := expandMounts(mounts)

	if len(sidecars) != 1 {
		t.Fatalf("expected 1 sidecar, got %d", len(sidecars))
	}

	sidecar := sidecars[0]
	if sidecar.Name != "sshfs-0" {
		t.Errorf("expected name 'sshfs-0', got '%s'", sidecar.Name)
	}
	if sidecar.Image != "alpine:latest" {
		t.Errorf("expected alpine:latest image, got '%s'", sidecar.Image)
	}
	if len(sidecar.Command) != 2 || sidecar.Command[0] != "sh" {
		t.Errorf("expected command 'sh -c', got %v", sidecar.Command)
	}
	if len(sidecar.Args) != 1 {
		t.Errorf("expected 1 arg, got %d", len(sidecar.Args))
	}
	// Check the sshfs command contains the host and path
	arg := sidecar.Args[0]
	if !strings.Contains(arg, "user@host.example.com") {
		t.Errorf("expected arg to contain 'user@host.example.com', got '%s'", arg)
	}
	if !strings.Contains(arg, "/data/notebooks") {
		t.Errorf("expected arg to contain '/data/notebooks', got '%s'", arg)
	}
}

func TestExpandMounts_MultipleMounts(t *testing.T) {
	mounts := []string{
		"sshfs://user1@host1:/path1",
		"sshfs://user2@host2:/path2",
	}

	sidecars := expandMounts(mounts)

	if len(sidecars) != 2 {
		t.Fatalf("expected 2 sidecars, got %d", len(sidecars))
	}

	if sidecars[0].Name != "sshfs-0" {
		t.Errorf("expected first sidecar name 'sshfs-0', got '%s'", sidecars[0].Name)
	}
	if sidecars[1].Name != "sshfs-1" {
		t.Errorf("expected second sidecar name 'sshfs-1', got '%s'", sidecars[1].Name)
	}
}

func TestExpandMounts_UnsupportedScheme(t *testing.T) {
	mounts := []string{
		"file:///local/path", // Not supported yet
		"cw://bucket/prefix", // Not supported yet
	}

	sidecars := expandMounts(mounts)

	// Should return empty - unsupported schemes are ignored
	if len(sidecars) != 0 {
		t.Errorf("expected 0 sidecars for unsupported schemes, got %d", len(sidecars))
	}
}

func TestExpandMounts_Rsync(t *testing.T) {
	mounts := []string{
		"rsync://user@host.example.com:/data/notebooks",
	}

	sidecars := expandMounts(mounts)

	if len(sidecars) != 1 {
		t.Fatalf("expected 1 sidecar, got %d", len(sidecars))
	}

	sidecar := sidecars[0]
	if sidecar.Name != "rsync-0" {
		t.Errorf("expected name 'rsync-0', got '%s'", sidecar.Name)
	}
	if sidecar.Image != "alpine:latest" {
		t.Errorf("expected alpine:latest image, got '%s'", sidecar.Image)
	}
	if len(sidecar.Command) != 2 || sidecar.Command[0] != "sh" {
		t.Errorf("expected command 'sh -c', got %v", sidecar.Command)
	}
	if len(sidecar.Args) != 1 {
		t.Errorf("expected 1 arg, got %d", len(sidecar.Args))
	}
	// Check the rsync command contains the host and path
	arg := sidecar.Args[0]
	if !strings.Contains(arg, "rsync") {
		t.Errorf("expected arg to contain 'rsync', got '%s'", arg)
	}
	if !strings.Contains(arg, "user@host.example.com") {
		t.Errorf("expected arg to contain 'user@host.example.com', got '%s'", arg)
	}
	if !strings.Contains(arg, "/data/notebooks") {
		t.Errorf("expected arg to contain '/data/notebooks', got '%s'", arg)
	}
}

func TestExpandMounts_MixedSchemes(t *testing.T) {
	mounts := []string{
		"sshfs://user1@host1:/path1",
		"rsync://user2@host2:/path2",
	}

	sidecars := expandMounts(mounts)

	if len(sidecars) != 2 {
		t.Fatalf("expected 2 sidecars, got %d", len(sidecars))
	}

	if sidecars[0].Name != "sshfs-0" {
		t.Errorf("expected first sidecar name 'sshfs-0', got '%s'", sidecars[0].Name)
	}
	if sidecars[1].Name != "rsync-1" {
		t.Errorf("expected second sidecar name 'rsync-1', got '%s'", sidecars[1].Name)
	}
}

func TestBuildPod_WithMounts(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Mounts: []string{
				"sshfs://user@host:/remote/data",
			},
			Storage: &marimov1alpha1.StorageSpec{
				Size: "1Gi",
			},
		},
	}

	pod := BuildPod(notebook)

	// Should have marimo + 1 sshfs sidecar
	if len(pod.Spec.Containers) != 2 {
		t.Fatalf("expected 2 containers, got %d", len(pod.Spec.Containers))
	}

	// First container should be marimo
	if pod.Spec.Containers[0].Name != "marimo" {
		t.Errorf("expected first container to be 'marimo', got '%s'", pod.Spec.Containers[0].Name)
	}

	// Second container should be sshfs sidecar
	sshfsSidecar := pod.Spec.Containers[1]
	if sshfsSidecar.Name != "sshfs-0" {
		t.Errorf("expected sidecar name 'sshfs-0', got '%s'", sshfsSidecar.Name)
	}
}

func TestParseRemoteMountURI_Basic(t *testing.T) {
	tests := []struct {
		name           string
		uri            string
		scheme         string
		wantUserHost   string
		wantSourcePath string
		wantMountPoint string
	}{
		{
			name:           "rsync basic",
			uri:            "rsync://user@host:/remote/path",
			scheme:         "rsync",
			wantUserHost:   "user@host",
			wantSourcePath: "/remote/path",
			wantMountPoint: "",
		},
		{
			name:           "rsync with custom mount",
			uri:            "rsync://user@host:/data:/mnt/custom",
			scheme:         "rsync",
			wantUserHost:   "user@host",
			wantSourcePath: "/data",
			wantMountPoint: "/mnt/custom",
		},
		{
			name:           "sshfs basic",
			uri:            "sshfs://admin@server:/files",
			scheme:         "sshfs",
			wantUserHost:   "admin@server",
			wantSourcePath: "/files",
			wantMountPoint: "",
		},
		{
			name:           "sshfs with custom mount",
			uri:            "sshfs://admin@server:/files:/home/marimo/data",
			scheme:         "sshfs",
			wantUserHost:   "admin@server",
			wantSourcePath: "/files",
			wantMountPoint: "/home/marimo/data",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			userHost, sourcePath, mountPoint := parseRemoteMountURI(tt.uri, tt.scheme)
			if userHost != tt.wantUserHost {
				t.Errorf("parseRemoteMountURI() userHost = %q, want %q", userHost, tt.wantUserHost)
			}
			if sourcePath != tt.wantSourcePath {
				t.Errorf("parseRemoteMountURI() sourcePath = %q, want %q", sourcePath, tt.wantSourcePath)
			}
			if mountPoint != tt.wantMountPoint {
				t.Errorf("parseRemoteMountURI() mountPoint = %q, want %q", mountPoint, tt.wantMountPoint)
			}
		})
	}
}

func TestExpandMounts_CustomMountPoint(t *testing.T) {
	// Test rsync with custom mount point
	mounts := []string{
		"rsync://user@host:/data:/mnt/custom",
	}

	sidecars := expandMounts(mounts)

	if len(sidecars) != 1 {
		t.Fatalf("expected 1 sidecar, got %d", len(sidecars))
	}

	// Check that the sidecar command contains the custom mount point
	args := sidecars[0].Args
	if len(args) != 1 {
		t.Fatalf("expected 1 arg, got %d", len(args))
	}

	if !strings.Contains(args[0], "/mnt/custom") {
		t.Errorf("expected args to contain '/mnt/custom', got %s", args[0])
	}
}

func TestExpandMounts_SSHFSCustomMountPoint(t *testing.T) {
	// Test sshfs with custom mount point
	mounts := []string{
		"sshfs://user@host:/data:/opt/data",
	}

	sidecars := expandMounts(mounts)

	if len(sidecars) != 1 {
		t.Fatalf("expected 1 sidecar, got %d", len(sidecars))
	}

	// Check that the sidecar command contains the custom mount point
	args := sidecars[0].Args
	if len(args) != 1 {
		t.Fatalf("expected 1 arg, got %d", len(args))
	}

	if !strings.Contains(args[0], "/opt/data") {
		t.Errorf("expected args to contain '/opt/data', got %s", args[0])
	}
}
