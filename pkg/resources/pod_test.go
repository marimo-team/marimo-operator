package resources

import (
	"strings"
	"testing"

	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	marimov1alpha1 "github.com/marimo-team/marimo-operator/api/v1alpha1"
)

const (
	testMarimoContainer = "marimo"
	testSetupVenv       = "setup-venv"
	testSSHDContainer   = "sshd"
	testSSHFSName       = "sshfs-0"
	testCWSidecarName   = "cw-0"
	testSSHPubkeyName   = "ssh-pubkey"
)

func TestBuildPod_BasicConfig(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      testNotebookName,
			Namespace: testNamespace,
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:  "ghcr.io/marimo-team/marimo:latest",
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
		},
	}

	pod := BuildPod(notebook)

	// Check metadata
	if pod.Name != testNotebookName {
		t.Errorf("expected pod name '%s', got '%s'", testNotebookName, pod.Name)
	}
	if pod.Namespace != testNamespace {
		t.Errorf("expected namespace '%s', got '%s'", testNamespace, pod.Namespace)
	}

	// Check labels
	if pod.Labels["app.kubernetes.io/name"] != testMarimoContainer {
		t.Errorf("expected label app.kubernetes.io/name='%s', got '%s'",
			testMarimoContainer, pod.Labels["app.kubernetes.io/name"])
	}
	if pod.Labels["app.kubernetes.io/instance"] != testNotebookName {
		t.Errorf(
			"expected label app.kubernetes.io/instance='%s', got '%s'",
			testNotebookName, pod.Labels["app.kubernetes.io/instance"])
	}

	// Check main container
	if len(pod.Spec.Containers) != 1 {
		t.Fatalf("expected 1 container, got %d", len(pod.Spec.Containers))
	}
	container := pod.Spec.Containers[0]
	if container.Name != testMarimoContainer {
		t.Errorf("expected container name '%s', got '%s'", testMarimoContainer, container.Name)
	}
	if container.Image != "ghcr.io/marimo-team/marimo:latest" {
		t.Errorf("expected image 'ghcr.io/marimo-team/marimo:latest', got '%s'", container.Image)
	}
	// Command should run marimo directly (no shell wrapper)
	if container.Command[0] != testMarimoContainer {
		t.Errorf("expected command '%s', got '%s'", testMarimoContainer, container.Command[0])
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
	if setupVenv.Name != testSetupVenv {
		t.Errorf("expected second init container name '%s', got '%s'",
			testSetupVenv, setupVenv.Name)
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
	if !strings.Contains(script, "if [ -d") || !strings.Contains(script, ".git ]") {
		t.Error("git-clone should check for existing .git directory")
	}
	if !strings.Contains(script, "skipping clone") {
		t.Error("git-clone should skip clone if repo exists")
	}
	if !strings.Contains(script, "git clone") {
		t.Error("git-clone should clone if repo doesn't exist")
	}

	// Check setup-venv init container
	setupVenv := pod.Spec.InitContainers[1]
	if setupVenv.Name != testSetupVenv {
		t.Errorf("expected second init container '%s', got '%s'",
			testSetupVenv, setupVenv.Name)
	}
	if setupVenv.Image != "ghcr.io/marimo-team/marimo:latest" {
		t.Errorf("setup-venv should use marimo image, got '%s'", setupVenv.Image)
	}
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
					Name:  testSSHDContainer,
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
	if pod.Spec.Containers[0].Name != testMarimoContainer {
		t.Errorf("expected first container to be '%s', got '%s'",
			testMarimoContainer, pod.Spec.Containers[0].Name)
	}

	// Check sidecar container
	sidecar := pod.Spec.Containers[1]
	if sidecar.Name != testSSHDContainer {
		t.Errorf("expected sidecar name '%s', got '%s'", testSSHDContainer, sidecar.Name)
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
					Name:       testSSHDContainer,
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
	if sidecar.Ports[0].Name != testSSHDContainer {
		t.Errorf("expected port name '%s', got '%s'", testSSHDContainer, sidecar.Ports[0].Name)
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
					Name:       testSSHDContainer,
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
	if pod.Spec.Containers[0].Name != testMarimoContainer {
		t.Errorf("expected first container '%s', got '%s'",
			testMarimoContainer, pod.Spec.Containers[0].Name)
	}
	if pod.Spec.Containers[1].Name != testSSHDContainer {
		t.Errorf("expected second container '%s', got '%s'",
			testSSHDContainer, pod.Spec.Containers[1].Name)
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

func TestExpandMounts_SSHFSIgnored(t *testing.T) {
	// sshfs:// mounts are handled by the plugin, not the operator
	mounts := []string{
		"sshfs:///home/marimo/notebooks",
	}

	sidecars := expandMounts(mounts)

	// sshfs:// should be ignored (plugin handles it)
	if len(sidecars) != 0 {
		t.Errorf("expected 0 sidecars for sshfs:// (handled by plugin), got %d", len(sidecars))
	}
}

func TestExpandMounts_UnsupportedScheme(t *testing.T) {
	mounts := []string{
		"file:///local/path", // Not supported yet
		"nfs://server/path",  // Not supported yet
	}

	sidecars := expandMounts(mounts)

	// Should return empty - unsupported schemes are ignored
	if len(sidecars) != 0 {
		t.Errorf("expected 0 sidecars for unsupported schemes, got %d", len(sidecars))
	}
}

func TestExpandMounts_RsyncIgnored(t *testing.T) {
	// rsync:// mounts are handled by the plugin, not the operator
	mounts := []string{
		"rsync://./local/data",
	}

	sidecars := expandMounts(mounts)

	// rsync:// should be ignored (plugin handles it)
	if len(sidecars) != 0 {
		t.Errorf("expected 0 sidecars for rsync:// (handled by plugin), got %d", len(sidecars))
	}
}

func TestExpandMounts_MixedSchemes(t *testing.T) {
	// Only cw:// should produce sidecars, sshfs:// and rsync:// are handled by plugin
	mounts := []string{
		"sshfs:///path1",
		"rsync://./path2",
		"cw://bucket/path3",
	}

	sidecars := expandMounts(mounts)

	// Only cw:// should produce sidecar
	if len(sidecars) != 1 {
		t.Fatalf("expected 1 sidecar (cw:// only), got %d", len(sidecars))
	}

	if sidecars[0].Name != "cw-2" {
		t.Errorf("expected sidecar name 'cw-2', got '%s'", sidecars[0].Name)
	}
}

func TestBuildPod_WithCWMounts(t *testing.T) {
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
				"cw://mybucket/data",
			},
			Storage: &marimov1alpha1.StorageSpec{
				Size: "1Gi",
			},
		},
	}

	pod := BuildPod(notebook)

	// Should have marimo + 1 cw sidecar
	if len(pod.Spec.Containers) != 2 {
		t.Fatalf("expected 2 containers, got %d", len(pod.Spec.Containers))
	}

	// First container should be marimo
	if pod.Spec.Containers[0].Name != testMarimoContainer {
		t.Errorf("expected first container to be '%s', got '%s'",
			testMarimoContainer, pod.Spec.Containers[0].Name)
	}

	// Second container should be cw sidecar
	cwSidecar := pod.Spec.Containers[1]
	if cwSidecar.Name != testCWSidecarName {
		t.Errorf("expected sidecar name '%s', got '%s'", testCWSidecarName, cwSidecar.Name)
	}
}

func TestParseCWMountURI(t *testing.T) {
	tests := []struct {
		uri        string
		bucket     string
		subpath    string
		mountPoint string
	}{
		{"cw://mybucket", "mybucket", "", ""},
		{"cw://mybucket/data", "mybucket", "data", ""},
		{"cw://mybucket/data/subdir", "mybucket", "data/subdir", ""},
		{"cw://mybucket/data:/mnt/s3", "mybucket", "data", "/mnt/s3"},
		{"cw://bucket:/custom", "bucket", "", "/custom"},
	}

	for _, tc := range tests {
		t.Run(tc.uri, func(t *testing.T) {
			bucket, subpath, mount := parseCWMountURI(tc.uri)
			if bucket != tc.bucket {
				t.Errorf("bucket: expected %q, got %q", tc.bucket, bucket)
			}
			if subpath != tc.subpath {
				t.Errorf("subpath: expected %q, got %q", tc.subpath, subpath)
			}
			if mount != tc.mountPoint {
				t.Errorf("mountPoint: expected %q, got %q", tc.mountPoint, mount)
			}
		})
	}
}

func TestExpandMounts_CW(t *testing.T) {
	mounts := []string{"cw://mybucket/data"}

	sidecars := expandMounts(mounts)

	if len(sidecars) != 1 {
		t.Fatalf("expected 1 sidecar, got %d", len(sidecars))
	}

	sidecar := sidecars[0]
	if sidecar.Name != testCWSidecarName {
		t.Errorf("expected name '%s', got %q", testCWSidecarName, sidecar.Name)
	}

	if !strings.Contains(sidecar.Image, "s3fs") {
		t.Errorf("expected image to contain 's3fs', got %q", sidecar.Image)
	}

	if len(sidecar.Args) != 1 {
		t.Fatalf("expected 1 arg, got %d", len(sidecar.Args))
	}

	// Check that the command contains the bucket path
	if !strings.Contains(sidecar.Args[0], "mybucket:/data") {
		t.Errorf("expected args to contain 'mybucket:/data', got %s", sidecar.Args[0])
	}

	// Check that it uses cwobject.com endpoint by default
	if !strings.Contains(sidecar.Args[0], "cwobject.com") {
		t.Errorf("expected args to contain 'cwobject.com', got %s", sidecar.Args[0])
	}
}

func TestExpandMounts_CWCustomMountPoint(t *testing.T) {
	mounts := []string{"cw://mybucket/data:/mnt/s3"}

	sidecars := expandMounts(mounts)

	if len(sidecars) != 1 {
		t.Fatalf("expected 1 sidecar, got %d", len(sidecars))
	}

	args := sidecars[0].Args
	if len(args) != 1 {
		t.Fatalf("expected 1 arg, got %d", len(args))
	}

	if !strings.Contains(args[0], "/mnt/s3") {
		t.Errorf("expected args to contain '/mnt/s3', got %s", args[0])
	}
}

func TestExpandMounts_CWBucketOnly(t *testing.T) {
	mounts := []string{"cw://mybucket"}

	sidecars := expandMounts(mounts)

	if len(sidecars) != 1 {
		t.Fatalf("expected 1 sidecar, got %d", len(sidecars))
	}

	args := sidecars[0].Args
	if len(args) != 1 {
		t.Fatalf("expected 1 arg, got %d", len(args))
	}

	// Should mount just the bucket (no :/ path)
	if !strings.Contains(args[0], "s3fs mybucket /home/marimo") {
		t.Errorf("expected args to contain 's3fs mybucket /home/marimo', got %s", args[0])
	}
}

func TestExpandMounts_CWSecretReference(t *testing.T) {
	mounts := []string{"cw://mybucket/data"}

	sidecars := expandMounts(mounts)

	if len(sidecars) != 1 {
		t.Fatalf("expected 1 sidecar, got %d", len(sidecars))
	}

	sidecar := sidecars[0]

	// Should have 2 env vars referencing the cw-credentials secret
	if len(sidecar.Env) != 2 {
		t.Fatalf("expected 2 env vars, got %d", len(sidecar.Env))
	}

	// Check AWS_ACCESS_KEY_ID
	accessKeyEnv := sidecar.Env[0]
	if accessKeyEnv.Name != "AWS_ACCESS_KEY_ID" {
		t.Errorf("expected first env var to be AWS_ACCESS_KEY_ID, got %s", accessKeyEnv.Name)
	}
	if accessKeyEnv.ValueFrom == nil || accessKeyEnv.ValueFrom.SecretKeyRef == nil {
		t.Fatal("expected AWS_ACCESS_KEY_ID to have secretKeyRef")
	}
	if accessKeyEnv.ValueFrom.SecretKeyRef.Name != CWCredentialsSecret {
		t.Errorf("expected secret name %q, got %q", CWCredentialsSecret, accessKeyEnv.ValueFrom.SecretKeyRef.Name)
	}

	// Check AWS_SECRET_ACCESS_KEY
	secretKeyEnv := sidecar.Env[1]
	if secretKeyEnv.Name != "AWS_SECRET_ACCESS_KEY" {
		t.Errorf("expected second env var to be AWS_SECRET_ACCESS_KEY, got %s", secretKeyEnv.Name)
	}
	if secretKeyEnv.ValueFrom == nil || secretKeyEnv.ValueFrom.SecretKeyRef == nil {
		t.Fatal("expected AWS_SECRET_ACCESS_KEY to have secretKeyRef")
	}
	if secretKeyEnv.ValueFrom.SecretKeyRef.Name != CWCredentialsSecret {
		t.Errorf("expected secret name %q, got %q", CWCredentialsSecret, secretKeyEnv.ValueFrom.SecretKeyRef.Name)
	}
}

func TestBuildPod_MountPropagation_WithFUSESidecar(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:   "ghcr.io/marimo-team/marimo:latest",
			Port:    2718,
			Content: ptrString("# test notebook"),
			Storage: &marimov1alpha1.StorageSpec{Size: "1Gi"},
			Mounts:  []string{"cw://mybucket"},
		},
	}

	pod := BuildPod(notebook)

	// Find marimo container
	var marimoContainer *corev1.Container
	var cwContainer *corev1.Container
	for i := range pod.Spec.Containers {
		if pod.Spec.Containers[i].Name == testMarimoContainer {
			marimoContainer = &pod.Spec.Containers[i]
		}
		if pod.Spec.Containers[i].Name == testCWSidecarName {
			cwContainer = &pod.Spec.Containers[i]
		}
	}

	if marimoContainer == nil {
		t.Fatal("marimo container not found")
	}
	if cwContainer == nil {
		t.Fatalf("%s container not found", testCWSidecarName)
	}

	// Check marimo has HostToContainer propagation on PVC mount
	for _, vm := range marimoContainer.VolumeMounts {
		if vm.Name == PVCVolumeName {
			if vm.MountPropagation == nil {
				t.Error("marimo container PVC mount should have MountPropagation set")
			} else if *vm.MountPropagation != corev1.MountPropagationHostToContainer {
				t.Errorf(
					"marimo container PVC mount should have HostToContainer propagation, got %v",
					*vm.MountPropagation)
			}
		}
	}

	// Check cw-0 has Bidirectional propagation on PVC mount
	for _, vm := range cwContainer.VolumeMounts {
		if vm.Name == PVCVolumeName {
			if vm.MountPropagation == nil {
				t.Error("cw-0 container PVC mount should have MountPropagation set")
			} else if *vm.MountPropagation != corev1.MountPropagationBidirectional {
				t.Errorf("cw-0 container PVC mount should have Bidirectional propagation, got %v", *vm.MountPropagation)
			}
		}
	}
}

func TestBuildPod_MountPropagation_WithoutFUSESidecar(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:   "ghcr.io/marimo-team/marimo:latest",
			Port:    2718,
			Content: ptrString("# test notebook"),
			Storage: &marimov1alpha1.StorageSpec{Size: "1Gi"},
			// No FUSE mounts
		},
	}

	pod := BuildPod(notebook)

	// Find marimo container
	var marimoContainer *corev1.Container
	for i := range pod.Spec.Containers {
		if pod.Spec.Containers[i].Name == testMarimoContainer {
			marimoContainer = &pod.Spec.Containers[i]
		}
	}

	if marimoContainer == nil {
		t.Fatal("marimo container not found")
	}

	// Check marimo does NOT have propagation set (no FUSE sidecars)
	for _, vm := range marimoContainer.VolumeMounts {
		if vm.Name == PVCVolumeName {
			if vm.MountPropagation != nil {
				t.Errorf(
					"marimo container PVC mount should NOT have MountPropagation "+
						"when no FUSE sidecars, got %v",
					*vm.MountPropagation)
			}
		}
	}
}

func TestBuildPod_SSHFSSidecar_SecretMount(t *testing.T) {
	// When a sidecar named "sshfs-*" is present, ssh-pubkey secret should be mounted
	port := int32(2222)
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:   "ghcr.io/marimo-team/marimo:latest",
			Port:    2718,
			Content: ptrString("# test notebook"),
			Storage: &marimov1alpha1.StorageSpec{Size: "1Gi"},
			Sidecars: []marimov1alpha1.SidecarSpec{
				{
					Name:       "sshfs-0",
					Image:      "linuxserver/openssh-server:latest",
					ExposePort: &port,
				},
			},
		},
	}

	pod := BuildPod(notebook)

	// Check ssh-pubkey volume exists
	var foundSSHPubkeyVolume bool
	for _, vol := range pod.Spec.Volumes {
		if vol.Name == testSSHPubkeyName {
			if vol.Secret == nil || vol.Secret.SecretName != testSSHPubkeyName {
				t.Errorf("%s volume should reference %s secret", testSSHPubkeyName, testSSHPubkeyName)
			}
			foundSSHPubkeyVolume = true
			break
		}
	}
	if !foundSSHPubkeyVolume {
		t.Errorf("expected %s volume to be present for sshfs sidecar", testSSHPubkeyName)
	}

	// Find sshfs sidecar and check it has the secret mounted
	var sshfsSidecar *corev1.Container
	for i := range pod.Spec.Containers {
		if pod.Spec.Containers[i].Name == "sshfs-0" {
			sshfsSidecar = &pod.Spec.Containers[i]
			break
		}
	}

	if sshfsSidecar == nil {
		t.Fatal("sshfs-0 container not found")
	}

	// Check ssh-pubkey is mounted at /config/ssh-pubkey
	var foundSSHPubkeyMount bool
	for _, vm := range sshfsSidecar.VolumeMounts {
		if vm.Name == testSSHPubkeyName && vm.MountPath == "/config/"+testSSHPubkeyName && vm.ReadOnly {
			foundSSHPubkeyMount = true
			break
		}
	}
	if !foundSSHPubkeyMount {
		t.Error("sshfs sidecar should have ssh-pubkey mounted at /config/ssh-pubkey")
	}
}

func TestBuildPod_NoSSHFSSidecar_NoSecretMount(t *testing.T) {
	// When no sshfs sidecar, ssh-pubkey secret should NOT be added
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Image:   "ghcr.io/marimo-team/marimo:latest",
			Port:    2718,
			Content: ptrString("# test notebook"),
			Storage: &marimov1alpha1.StorageSpec{Size: "1Gi"},
			// No sidecars
		},
	}

	pod := BuildPod(notebook)

	// Check ssh-pubkey volume does NOT exist
	for _, vol := range pod.Spec.Volumes {
		if vol.Name == testSSHPubkeyName {
			t.Errorf("%s volume should NOT be present when no sshfs sidecar", testSSHPubkeyName)
		}
	}
}
