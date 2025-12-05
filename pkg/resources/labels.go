package resources

import (
	marimov1alpha1 "github.com/marimo-team/marimo-operator/api/v1alpha1"
)

// Labels returns standard labels for a MarimoNotebook's resources.
func Labels(notebook *marimov1alpha1.MarimoNotebook) map[string]string {
	return map[string]string{
		"app.kubernetes.io/name":       "marimo",
		"app.kubernetes.io/instance":   notebook.Name,
		"app.kubernetes.io/managed-by": "marimo-operator",
	}
}
