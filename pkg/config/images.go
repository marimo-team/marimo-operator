// Package config provides configuration for the marimo-operator.
package config

import "os"

// Default images for operator-managed containers.
// All can be overridden via environment variables.
var (
	// DefaultInitImage is used for init containers (copy-content).
	DefaultInitImage = getEnvOrDefault("DEFAULT_INIT_IMAGE", "busybox:1.36")

	// GitImage is used for git clone sidecars.
	GitImage = getEnvOrDefault("GIT_IMAGE", "alpine/git:latest")

	// AlpineImage is used for sshfs and file:// mount sidecars.
	AlpineImage = getEnvOrDefault("ALPINE_IMAGE", "alpine:latest")

	// S3FSImage is used for cw:// (CoreWeave S3) mount sidecars.
	S3FSImage = getEnvOrDefault("S3FS_IMAGE", "ghcr.io/marimo-team/marimo-operator/s3fs:latest")
)

func getEnvOrDefault(key, defaultValue string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultValue
}
