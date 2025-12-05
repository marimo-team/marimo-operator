package resources

import (
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	marimov1alpha1 "github.com/marimo-team/marimo-operator/api/v1alpha1"
)

func TestBuildService_BasicConfig(t *testing.T) {
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

	svc := BuildService(notebook)

	// Check metadata
	if svc.Name != "test-notebook" {
		t.Errorf("expected service name 'test-notebook', got '%s'", svc.Name)
	}
	if svc.Namespace != "default" {
		t.Errorf("expected namespace 'default', got '%s'", svc.Namespace)
	}

	// Check labels
	if svc.Labels["app.kubernetes.io/name"] != "marimo" {
		t.Errorf("expected label app.kubernetes.io/name='marimo', got '%s'", svc.Labels["app.kubernetes.io/name"])
	}
	if svc.Labels["app.kubernetes.io/instance"] != "test-notebook" {
		t.Errorf("expected label app.kubernetes.io/instance='test-notebook', got '%s'", svc.Labels["app.kubernetes.io/instance"])
	}

	// Check selector
	if svc.Spec.Selector["app.kubernetes.io/instance"] != "test-notebook" {
		t.Errorf("expected selector app.kubernetes.io/instance='test-notebook', got '%s'", svc.Spec.Selector["app.kubernetes.io/instance"])
	}

	// Check service type
	if svc.Spec.Type != corev1.ServiceTypeClusterIP {
		t.Errorf("expected service type ClusterIP, got '%s'", svc.Spec.Type)
	}

	// Check ports
	if len(svc.Spec.Ports) != 1 {
		t.Fatalf("expected 1 port, got %d", len(svc.Spec.Ports))
	}
	port := svc.Spec.Ports[0]
	if port.Name != "http" {
		t.Errorf("expected port name 'http', got '%s'", port.Name)
	}
	if port.Port != 2718 {
		t.Errorf("expected port 2718, got %d", port.Port)
	}
	if port.TargetPort.IntVal != 2718 {
		t.Errorf("expected targetPort 2718, got %d", port.TargetPort.IntVal)
	}
	if port.Protocol != corev1.ProtocolTCP {
		t.Errorf("expected protocol TCP, got '%s'", port.Protocol)
	}
}

func TestBuildService_CustomPort(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Port:   8080,
			Source: "https://github.com/marimo-team/marimo.git",
		},
	}

	svc := BuildService(notebook)

	if len(svc.Spec.Ports) != 1 {
		t.Fatalf("expected 1 port, got %d", len(svc.Spec.Ports))
	}
	if svc.Spec.Ports[0].Port != 8080 {
		t.Errorf("expected port 8080, got %d", svc.Spec.Ports[0].Port)
	}
	if svc.Spec.Ports[0].TargetPort.IntVal != 8080 {
		t.Errorf("expected targetPort 8080, got %d", svc.Spec.Ports[0].TargetPort.IntVal)
	}
}

func TestBuildService_WithSidecarPorts(t *testing.T) {
	sshPort := int32(2222)
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Sidecars: []marimov1alpha1.SidecarSpec{
				{
					Name:       "sshd",
					Image:      "linuxserver/openssh-server:latest",
					ExposePort: &sshPort,
				},
			},
		},
	}

	svc := BuildService(notebook)

	// Should have 2 ports: http (2718) and sshd (2222)
	if len(svc.Spec.Ports) != 2 {
		t.Fatalf("expected 2 ports, got %d", len(svc.Spec.Ports))
	}

	// Check http port
	var httpPort, sshdPort *corev1.ServicePort
	for i := range svc.Spec.Ports {
		p := &svc.Spec.Ports[i]
		switch p.Name {
		case "http":
			httpPort = p
		case "sshd":
			sshdPort = p
		}
	}

	if httpPort == nil {
		t.Fatal("expected http port")
	}
	if httpPort.Port != 2718 {
		t.Errorf("expected http port 2718, got %d", httpPort.Port)
	}

	if sshdPort == nil {
		t.Fatal("expected sshd port")
	}
	if sshdPort.Port != 2222 {
		t.Errorf("expected sshd port 2222, got %d", sshdPort.Port)
	}
	if sshdPort.TargetPort.IntVal != 2222 {
		t.Errorf("expected sshd targetPort 2222, got %d", sshdPort.TargetPort.IntVal)
	}
}

func TestBuildService_SidecarWithoutExposePort(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Sidecars: []marimov1alpha1.SidecarSpec{
				{
					Name:  "helper",
					Image: "helper:latest",
					// No ExposePort - should not add to service
				},
			},
		},
	}

	svc := BuildService(notebook)

	// Should only have 1 port (http)
	if len(svc.Spec.Ports) != 1 {
		t.Fatalf("expected 1 port (sidecar without ExposePort should not add ports), got %d", len(svc.Spec.Ports))
	}
	if svc.Spec.Ports[0].Name != "http" {
		t.Errorf("expected only 'http' port, got '%s'", svc.Spec.Ports[0].Name)
	}
}

func TestBuildService_MultipleSidecarsWithPorts(t *testing.T) {
	sshPort := int32(2222)
	gitPort := int32(9418)
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Port:   2718,
			Source: "https://github.com/marimo-team/marimo.git",
			Sidecars: []marimov1alpha1.SidecarSpec{
				{
					Name:       "sshd",
					Image:      "openssh:latest",
					ExposePort: &sshPort,
				},
				{
					Name:       "git-daemon",
					Image:      "git:latest",
					ExposePort: &gitPort,
				},
			},
		},
	}

	svc := BuildService(notebook)

	// Should have 3 ports: http, sshd, git-daemon
	if len(svc.Spec.Ports) != 3 {
		t.Fatalf("expected 3 ports, got %d", len(svc.Spec.Ports))
	}

	portNames := make(map[string]int32)
	for _, p := range svc.Spec.Ports {
		portNames[p.Name] = p.Port
	}

	if portNames["http"] != 2718 {
		t.Errorf("expected http port 2718, got %d", portNames["http"])
	}
	if portNames["sshd"] != 2222 {
		t.Errorf("expected sshd port 2222, got %d", portNames["sshd"])
	}
	if portNames["git-daemon"] != 9418 {
		t.Errorf("expected git-daemon port 9418, got %d", portNames["git-daemon"])
	}
}

func TestLabels(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "my-notebook",
			Namespace: "default",
		},
	}

	labels := Labels(notebook)

	expected := map[string]string{
		"app.kubernetes.io/name":       "marimo",
		"app.kubernetes.io/instance":   "my-notebook",
		"app.kubernetes.io/managed-by": "marimo-operator",
	}

	for key, expectedVal := range expected {
		if labels[key] != expectedVal {
			t.Errorf("expected label %s='%s', got '%s'", key, expectedVal, labels[key])
		}
	}
}
