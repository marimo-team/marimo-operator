package resources

import (
	"crypto/sha256"
	"fmt"
	"path/filepath"
	"strings"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	marimov1alpha1 "github.com/marimo-team/marimo-operator/api/v1alpha1"
)

const (
	// ConfigMapVolumeName is the name used for the content ConfigMap volume.
	ConfigMapVolumeName = "notebook-content"
	// ContentKey is the key used in ConfigMap for notebook content.
	ContentKey = "notebook.py"
)

// BuildConfigMap creates a ConfigMap containing the notebook content.
// Returns nil if content is not specified (source is used instead).
func BuildConfigMap(notebook *marimov1alpha1.MarimoNotebook) *corev1.ConfigMap {
	if notebook.Spec.Content == nil {
		return nil
	}

	return &corev1.ConfigMap{
		ObjectMeta: metav1.ObjectMeta{
			Name:      ConfigMapName(notebook.Name),
			Namespace: notebook.Namespace,
			Labels:    Labels(notebook),
		},
		Data: map[string]string{
			ContentKey: *notebook.Spec.Content,
		},
	}
}

// ConfigMapName returns the name for the content ConfigMap.
func ConfigMapName(notebookName string) string {
	return notebookName + "-content"
}

// ContentHash computes a SHA256 hash of the content for change detection.
func ContentHash(content string) string {
	hash := sha256.Sum256([]byte(content))
	return fmt.Sprintf("sha256:%x", hash[:8]) // First 8 bytes = 16 hex chars
}

// DetectContentKey determines the ConfigMap key based on content type.
// Returns "notebook.py" for Python content, "notebook.md" for markdown.
func DetectContentKey(content string) string {
	trimmed := strings.TrimSpace(content)

	// Check for markdown frontmatter
	if strings.HasPrefix(trimmed, "---") {
		return "notebook.md"
	}

	// Check for marimo Python patterns
	if strings.Contains(content, "@app.cell") ||
		strings.Contains(content, "import marimo") ||
		strings.Contains(content, "marimo.App") {
		return "notebook.py"
	}

	// Default to Python
	return "notebook.py"
}

// NotebookFilename returns just the filename for the notebook in the container.
func NotebookFilename(content string) string {
	return filepath.Base(DetectContentKey(content))
}
