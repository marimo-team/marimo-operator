package v1alpha1

import (
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// StorageSpec defines persistent storage configuration.
type StorageSpec struct {
	// Size of the PVC (e.g., "1Gi", "10Gi")
	// +kubebuilder:default:="1Gi"
	Size string `json:"size,omitempty"`

	// StorageClassName for the PVC (uses cluster default if empty)
	// +optional
	StorageClassName *string `json:"storageClassName,omitempty"`
}

// ResourcesSpec defines compute resources for the notebook container.
type ResourcesSpec struct {
	// Requests specifies minimum resources required
	// +optional
	Requests corev1.ResourceList `json:"requests,omitempty"`

	// Limits specifies maximum resources allowed
	// +optional
	Limits corev1.ResourceList `json:"limits,omitempty"`
}

// AuthSpec defines authentication configuration.
type AuthSpec struct {
	// Password references a Secret containing the marimo password
	// +optional
	Password *SecretKeySelector `json:"password,omitempty"`
}

// SecretKeySelector selects a key from a Secret.
type SecretKeySelector struct {
	// Name of the Secret
	SecretKeyRef corev1.SecretKeySelector `json:"secretKeyRef"`
}

// SidecarSpec defines an additional container that runs alongside marimo.
type SidecarSpec struct {
	// Name of the sidecar container (must be unique)
	// +kubebuilder:validation:Required
	Name string `json:"name"`

	// Image to use for the sidecar
	// +kubebuilder:validation:Required
	Image string `json:"image"`

	// ExposePort adds this port to the Service for external access
	// +optional
	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:validation:Maximum=65535
	ExposePort *int32 `json:"exposePort,omitempty"`

	// Env variables for the sidecar
	// +optional
	Env []corev1.EnvVar `json:"env,omitempty"`

	// Command overrides the container entrypoint
	// +optional
	Command []string `json:"command,omitempty"`

	// Args to pass to the command
	// +optional
	Args []string `json:"args,omitempty"`

	// Resources for the sidecar container
	// +optional
	Resources *corev1.ResourceRequirements `json:"resources,omitempty"`

	// SecurityContext for the sidecar container
	// Required for FUSE-based mounts (s3fs, sshfs) which need privileged access
	// +optional
	SecurityContext *corev1.SecurityContext `json:"securityContext,omitempty"`
}

// MarimoNotebookSpec defines the desired state of MarimoNotebook.
// +kubebuilder:validation:XValidation:rule="!(has(self.sidecars) && size(self.sidecars) > 0 && !has(self.storage))",message="storage is required when sidecars are specified"
// +kubebuilder:validation:XValidation:rule="!(has(self.source) && has(self.content))",message="source and content are mutually exclusive"
type MarimoNotebookSpec struct {
	// Image for marimo container
	// +kubebuilder:default:="ghcr.io/marimo-team/marimo:latest"
	// +optional
	Image string `json:"image,omitempty"`

	// Port for marimo server
	// +kubebuilder:default:=2718
	// +kubebuilder:validation:Minimum=1
	// +kubebuilder:validation:Maximum=65535
	// +optional
	Port int32 `json:"port,omitempty"`

	// Source is a Git URL to clone notebook content from
	// The repository is cloned into the PVC via an init container
	// +optional
	Source string `json:"source,omitempty"`

	// Content is inline notebook content (marimo .py or .md format)
	// When set, operator creates a ConfigMap and mounts it
	// +optional
	Content *string `json:"content,omitempty"`

	// Storage configures persistent storage for notebooks
	// +optional
	Storage *StorageSpec `json:"storage,omitempty"`

	// Resources for the marimo container
	// +optional
	Resources *ResourcesSpec `json:"resources,omitempty"`

	// Auth configures authentication
	// +optional
	Auth *AuthSpec `json:"auth,omitempty"`

	// Mode is the marimo server mode: "edit" (default) or "run"
	// +kubebuilder:default:="edit"
	// +kubebuilder:validation:Enum=edit;run
	// +optional
	Mode string `json:"mode,omitempty"`

	// Env variables for the marimo container
	// +optional
	Env []corev1.EnvVar `json:"env,omitempty"`

	// Mounts are high-level data source URIs expanded to sidecars
	// Supported schemes: cw://, sshfs://, rsync://
	// +optional
	Mounts []string `json:"mounts,omitempty"`

	// Sidecars are additional containers that run alongside marimo
	// They share the PVC volume mounted at /data
	// +optional
	Sidecars []SidecarSpec `json:"sidecars,omitempty"`

	// PodOverrides allows customizing the pod spec via strategic merge patch
	// Use this for advanced configuration like nodeSelector, tolerations, etc.
	// +optional
	// +kubebuilder:validation:Schemaless
	// +kubebuilder:pruning:PreserveUnknownFields
	PodOverrides *corev1.PodSpec `json:"podOverrides,omitempty"`
}

// MarimoNotebookPhase represents the current phase of the notebook.
// +kubebuilder:validation:Enum=Pending;Running;Failed
type MarimoNotebookPhase string

const (
	// PhasePending indicates the notebook resources are being created.
	PhasePending MarimoNotebookPhase = "Pending"
	// PhaseRunning indicates the notebook pod is running.
	PhaseRunning MarimoNotebookPhase = "Running"
	// PhaseFailed indicates the notebook failed to start.
	PhaseFailed MarimoNotebookPhase = "Failed"
)

// MarimoNotebookStatus defines the observed state of MarimoNotebook.
type MarimoNotebookStatus struct {
	// Phase of the notebook (Pending, Running, Failed)
	// +optional
	Phase MarimoNotebookPhase `json:"phase,omitempty"`

	// URL to access the notebook (internal service URL)
	// +optional
	URL string `json:"url,omitempty"`

	// SourceHash is a hash of the source URL for change detection
	// +optional
	SourceHash string `json:"sourceHash,omitempty"`

	// PodName is the name of the created Pod
	// +optional
	PodName string `json:"podName,omitempty"`

	// ServiceName is the name of the created Service
	// +optional
	ServiceName string `json:"serviceName,omitempty"`

	// Conditions represent the latest available observations
	// +optional
	Conditions []metav1.Condition `json:"conditions,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:singular=marimo,shortName=mo,path=marimos
// +kubebuilder:printcolumn:name="Phase",type=string,JSONPath=`.status.phase`
// +kubebuilder:printcolumn:name="URL",type=string,JSONPath=`.status.url`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// MarimoNotebook is the Schema for the marimos API.
// It deploys a marimo notebook server with optional sidecars and persistent storage.
type MarimoNotebook struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   MarimoNotebookSpec   `json:"spec,omitempty"`
	Status MarimoNotebookStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// MarimoNotebookList contains a list of MarimoNotebook.
type MarimoNotebookList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []MarimoNotebook `json:"items"`
}

func init() {
	SchemeBuilder.Register(&MarimoNotebook{}, &MarimoNotebookList{})
}
