package resources

import (
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/intstr"

	marimov1alpha1 "github.com/marimo-team/marimo-operator/api/v1alpha1"
)

// BuildService creates a Service spec for a MarimoNotebook.
func BuildService(notebook *marimov1alpha1.MarimoNotebook) *corev1.Service {
	ports := []corev1.ServicePort{
		{
			Name:       "http",
			Port:       notebook.Spec.Port,
			TargetPort: intstr.FromInt32(notebook.Spec.Port),
			Protocol:   corev1.ProtocolTCP,
		},
	}

	// Expose sidecar ports if configured
	for _, sidecar := range notebook.Spec.Sidecars {
		if sidecar.ExposePort != nil {
			ports = append(ports, corev1.ServicePort{
				Name:       sidecar.Name,
				Port:       *sidecar.ExposePort,
				TargetPort: intstr.FromInt32(*sidecar.ExposePort),
				Protocol:   corev1.ProtocolTCP,
			})
		}
	}

	return &corev1.Service{
		ObjectMeta: metav1.ObjectMeta{
			Name:      notebook.Name,
			Namespace: notebook.Namespace,
			Labels:    Labels(notebook),
		},
		Spec: corev1.ServiceSpec{
			Type:     corev1.ServiceTypeClusterIP,
			Selector: Labels(notebook),
			Ports:    ports,
		},
	}
}
