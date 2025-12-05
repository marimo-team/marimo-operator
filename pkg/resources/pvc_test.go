package resources

import (
	"testing"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	marimov1alpha1 "github.com/marimo-team/marimo-operator/api/v1alpha1"
)

func TestBuildPVC_NilStorage(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Source: "https://github.com/marimo-team/marimo.git",
			// No storage configured
		},
	}

	pvc := BuildPVC(notebook)

	if pvc != nil {
		t.Error("expected nil PVC when storage is not configured")
	}
}

func TestBuildPVC_DefaultSize(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Source:  "https://github.com/marimo-team/marimo.git",
			Storage: &marimov1alpha1.StorageSpec{
				// Size not specified, should use default
			},
		},
	}

	pvc := BuildPVC(notebook)

	if pvc == nil {
		t.Fatal("expected PVC to be created")
	}

	// Check metadata
	if pvc.Name != "test-notebook" {
		t.Errorf("expected PVC name 'test-notebook', got '%s'", pvc.Name)
	}
	if pvc.Namespace != "default" {
		t.Errorf("expected namespace 'default', got '%s'", pvc.Namespace)
	}

	// Check labels
	if pvc.Labels["app.kubernetes.io/name"] != "marimo" {
		t.Errorf("expected label app.kubernetes.io/name='marimo', got '%s'", pvc.Labels["app.kubernetes.io/name"])
	}
	if pvc.Labels["app.kubernetes.io/instance"] != "test-notebook" {
		t.Errorf("expected label app.kubernetes.io/instance='test-notebook', got '%s'", pvc.Labels["app.kubernetes.io/instance"])
	}

	// Check access mode
	if len(pvc.Spec.AccessModes) != 1 || pvc.Spec.AccessModes[0] != corev1.ReadWriteOnce {
		t.Errorf("expected ReadWriteOnce access mode, got %v", pvc.Spec.AccessModes)
	}

	// Check default size
	storageRequest := pvc.Spec.Resources.Requests[corev1.ResourceStorage]
	if storageRequest.String() != "1Gi" {
		t.Errorf("expected default storage size '1Gi', got '%s'", storageRequest.String())
	}

	// Check no storage class (uses cluster default)
	if pvc.Spec.StorageClassName != nil {
		t.Errorf("expected nil storage class (cluster default), got '%s'", *pvc.Spec.StorageClassName)
	}
}

func TestBuildPVC_CustomSize(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Source: "https://github.com/marimo-team/marimo.git",
			Storage: &marimov1alpha1.StorageSpec{
				Size: "10Gi",
			},
		},
	}

	pvc := BuildPVC(notebook)

	if pvc == nil {
		t.Fatal("expected PVC to be created")
	}

	storageRequest := pvc.Spec.Resources.Requests[corev1.ResourceStorage]
	if storageRequest.String() != "10Gi" {
		t.Errorf("expected storage size '10Gi', got '%s'", storageRequest.String())
	}
}

func TestBuildPVC_CustomStorageClass(t *testing.T) {
	storageClass := "fast-ssd"
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Source: "https://github.com/marimo-team/marimo.git",
			Storage: &marimov1alpha1.StorageSpec{
				Size:             "5Gi",
				StorageClassName: &storageClass,
			},
		},
	}

	pvc := BuildPVC(notebook)

	if pvc == nil {
		t.Fatal("expected PVC to be created")
	}

	if pvc.Spec.StorageClassName == nil {
		t.Fatal("expected storage class to be set")
	}
	if *pvc.Spec.StorageClassName != "fast-ssd" {
		t.Errorf("expected storage class 'fast-ssd', got '%s'", *pvc.Spec.StorageClassName)
	}

	storageRequest := pvc.Spec.Resources.Requests[corev1.ResourceStorage]
	if storageRequest.String() != "5Gi" {
		t.Errorf("expected storage size '5Gi', got '%s'", storageRequest.String())
	}
}
