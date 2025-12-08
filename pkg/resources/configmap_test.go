package resources

import (
	"strings"
	"testing"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"

	marimov1alpha1 "github.com/marimo-team/marimo-operator/api/v1alpha1"
)

func TestBuildConfigMap_WithContent(t *testing.T) {
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
			Content: &content,
		},
	}

	cm := BuildConfigMap(notebook)

	if cm == nil {
		t.Fatal("expected ConfigMap, got nil")
	}

	// Check metadata
	if cm.Name != "test-notebook-content" {
		t.Errorf("expected name 'test-notebook-content', got '%s'", cm.Name)
	}
	if cm.Namespace != "default" {
		t.Errorf("expected namespace 'default', got '%s'", cm.Namespace)
	}

	// Check labels
	if cm.Labels["app.kubernetes.io/instance"] != "test-notebook" {
		t.Errorf("expected label app.kubernetes.io/instance='test-notebook', got '%s'", cm.Labels["app.kubernetes.io/instance"])
	}

	// Check data
	if cm.Data[ContentKey] != content {
		t.Errorf("expected content in ConfigMap, got '%s'", cm.Data[ContentKey])
	}
}

func TestBuildConfigMap_WithoutContent(t *testing.T) {
	notebook := &marimov1alpha1.MarimoNotebook{
		ObjectMeta: metav1.ObjectMeta{
			Name:      "test-notebook",
			Namespace: "default",
		},
		Spec: marimov1alpha1.MarimoNotebookSpec{
			Source: "https://github.com/marimo-team/marimo.git",
		},
	}

	cm := BuildConfigMap(notebook)

	if cm != nil {
		t.Error("expected nil ConfigMap when content is not specified")
	}
}

func TestConfigMapName(t *testing.T) {
	name := ConfigMapName("my-notebook")
	if name != "my-notebook-content" {
		t.Errorf("expected 'my-notebook-content', got '%s'", name)
	}
}

func TestContentHash(t *testing.T) {
	content := "import marimo as mo"
	hash := ContentHash(content)

	// Should start with sha256:
	if !strings.HasPrefix(hash, "sha256:") {
		t.Errorf("expected hash to start with 'sha256:', got '%s'", hash)
	}

	// Should be consistent
	hash2 := ContentHash(content)
	if hash != hash2 {
		t.Error("content hash should be deterministic")
	}

	// Different content should have different hash
	hash3 := ContentHash("different content")
	if hash == hash3 {
		t.Error("different content should have different hash")
	}
}

func TestDetectContentKey_Python(t *testing.T) {
	tests := []struct {
		name     string
		content  string
		expected string
	}{
		{
			name:     "import marimo",
			content:  "import marimo as mo\n\napp = mo.App()",
			expected: "notebook.py",
		},
		{
			name:     "app.cell decorator",
			content:  "@app.cell\ndef hello():\n    pass",
			expected: "notebook.py",
		},
		{
			name:     "marimo.App reference",
			content:  "app = marimo.App()",
			expected: "notebook.py",
		},
		{
			name:     "unknown content defaults to py",
			content:  "print('hello')",
			expected: "notebook.py",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			key := DetectContentKey(tt.content)
			if key != tt.expected {
				t.Errorf("expected '%s', got '%s'", tt.expected, key)
			}
		})
	}
}

func TestDetectContentKey_Markdown(t *testing.T) {
	content := `---
title: My Notebook
---

# Hello World

This is a marimo markdown notebook.
`
	key := DetectContentKey(content)
	if key != "notebook.md" {
		t.Errorf("expected 'notebook.md', got '%s'", key)
	}
}

func TestNotebookFilename(t *testing.T) {
	pyContent := "import marimo as mo"
	if NotebookFilename(pyContent) != "notebook.py" {
		t.Errorf("expected 'notebook.py', got '%s'", NotebookFilename(pyContent))
	}

	mdContent := "---\ntitle: test\n---\n# Hello"
	if NotebookFilename(mdContent) != "notebook.md" {
		t.Errorf("expected 'notebook.md', got '%s'", NotebookFilename(mdContent))
	}
}
