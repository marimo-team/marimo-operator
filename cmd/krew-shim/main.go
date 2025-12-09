// Package main provides a krew-compatible kubectl plugin shim.
// It delegates to uvx kubectl-marimo for the actual implementation.
package main

import (
	"fmt"
	"os"
	"os/exec"
	"syscall"
)

// Version is the kubectl-marimo PyPI package version to use.
// This should be updated when publishing new releases.
const Version = "0.1.0"

func main() {
	// Find uvx in PATH
	uvx, err := exec.LookPath("uvx")
	if err != nil {
		fmt.Fprintln(os.Stderr, "Error: uvx not found in PATH")
		fmt.Fprintln(os.Stderr, "Install uv: https://docs.astral.sh/uv/getting-started/installation/")
		os.Exit(1)
	}

	// Build args: uvx kubectl-marimo@VERSION <args...>
	pkg := fmt.Sprintf("kubectl-marimo@%s", Version)
	args := append([]string{"uvx", pkg}, os.Args[1:]...)

	// Replace current process with uvx
	if err := syscall.Exec(uvx, args, os.Environ()); err != nil {
		fmt.Fprintf(os.Stderr, "Error: failed to exec uvx: %v\n", err)
		os.Exit(1)
	}
}
