package resources

import (
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/resource"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	marimov1alpha1 "github.com/marimo-team/marimo-operator/api/v1alpha1"
)

const (
	// DefaultStorageSize is the default PVC size if not specified.
	DefaultStorageSize = "1Gi"
	// PVCVolumeName is the name used for the PVC volume in pods.
	PVCVolumeName = "notebook-data"
)

// BuildPVC creates a PersistentVolumeClaim for a MarimoNotebook.
// Returns nil if storage is not configured.
func BuildPVC(notebook *marimov1alpha1.MarimoNotebook) *corev1.PersistentVolumeClaim {
	if notebook.Spec.Storage == nil {
		return nil
	}

	size := notebook.Spec.Storage.Size
	if size == "" {
		size = DefaultStorageSize
	}

	pvc := &corev1.PersistentVolumeClaim{
		ObjectMeta: metav1.ObjectMeta{
			Name:      notebook.Name,
			Namespace: notebook.Namespace,
			Labels:    Labels(notebook),
		},
		Spec: corev1.PersistentVolumeClaimSpec{
			AccessModes: []corev1.PersistentVolumeAccessMode{
				corev1.ReadWriteOnce,
			},
			Resources: corev1.VolumeResourceRequirements{
				Requests: corev1.ResourceList{
					corev1.ResourceStorage: resource.MustParse(size),
				},
			},
		},
	}

	// Set storage class if specified
	if notebook.Spec.Storage.StorageClassName != nil {
		pvc.Spec.StorageClassName = notebook.Spec.Storage.StorageClassName
	}

	return pvc
}
