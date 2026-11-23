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

	// Expose all sidecar container ports
	for _, sidecar := range notebook.Spec.Sidecars {
		for _, port := range sidecar.Ports {
			protocol := port.Protocol
			if protocol == "" {
				protocol = corev1.ProtocolTCP
			}
			ports = append(ports, corev1.ServicePort{
				Name:       port.Name,
				Port:       port.ContainerPort,
				TargetPort: intstr.FromInt32(port.ContainerPort),
				Protocol:   protocol,
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
