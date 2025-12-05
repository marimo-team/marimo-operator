/*
Copyright 2025.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package controller

import (
	"context"
	"crypto/sha256"
	"fmt"

	corev1 "k8s.io/api/core/v1"
	k8serrors "k8s.io/apimachinery/pkg/api/errors"
	"k8s.io/apimachinery/pkg/runtime"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	logf "sigs.k8s.io/controller-runtime/pkg/log"

	marimov1alpha1 "github.com/marimo-team/marimo-operator/api/v1alpha1"
	"github.com/marimo-team/marimo-operator/pkg/resources"
)

// MarimoNotebookReconciler reconciles a MarimoNotebook object
type MarimoNotebookReconciler struct {
	client.Client
	Scheme *runtime.Scheme
}

// +kubebuilder:rbac:groups=marimo.io,resources=marimos,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=marimo.io,resources=marimos/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=marimo.io,resources=marimos/finalizers,verbs=update
// +kubebuilder:rbac:groups="",resources=pods,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=services,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=persistentvolumeclaims,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=configmaps,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=events,verbs=create;patch

// Reconcile is part of the main kubernetes reconciliation loop which aims to
// move the current state of the cluster closer to the desired state.
func (r *MarimoNotebookReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := logf.FromContext(ctx)

	// 1. Fetch the MarimoNotebook
	notebook := &marimov1alpha1.MarimoNotebook{}
	if err := r.Get(ctx, req.NamespacedName, notebook); err != nil {
		if k8serrors.IsNotFound(err) {
			logger.V(1).Info("MarimoNotebook not found, skipping")
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	// 2. Handle deletion (owner references handle cleanup)
	if !notebook.DeletionTimestamp.IsZero() {
		logger.Info("MarimoNotebook is being deleted")
		return ctrl.Result{}, nil
	}

	// 3. Reconcile ConfigMap (if content specified)
	if err := r.reconcileConfigMap(ctx, notebook); err != nil {
		logger.Error(err, "Failed to reconcile ConfigMap")
		return ctrl.Result{}, err
	}

	// 4. Reconcile PVC (if storage configured)
	if err := r.reconcilePVC(ctx, notebook); err != nil {
		logger.Error(err, "Failed to reconcile PVC")
		return ctrl.Result{}, err
	}

	// 5. Reconcile Pod
	pod, err := r.reconcilePod(ctx, notebook)
	if err != nil {
		logger.Error(err, "Failed to reconcile Pod")
		return ctrl.Result{}, err
	}

	// 6. Reconcile Service
	svc, err := r.reconcileService(ctx, notebook)
	if err != nil {
		logger.Error(err, "Failed to reconcile Service")
		return ctrl.Result{}, err
	}

	// 7. Update Status
	return r.updateStatus(ctx, notebook, pod, svc)
}

func (r *MarimoNotebookReconciler) reconcileConfigMap(ctx context.Context, notebook *marimov1alpha1.MarimoNotebook) error {
	// Skip if no content specified (using source instead)
	if notebook.Spec.Content == nil {
		return nil
	}

	logger := logf.FromContext(ctx)
	desired := resources.BuildConfigMap(notebook)
	if desired == nil {
		return nil
	}

	// Set owner reference for automatic garbage collection
	if err := controllerutil.SetControllerReference(notebook, desired, r.Scheme); err != nil {
		return err
	}

	// Check if ConfigMap exists
	existing := &corev1.ConfigMap{}
	err := r.Get(ctx, client.ObjectKeyFromObject(desired), existing)
	if err != nil {
		if k8serrors.IsNotFound(err) {
			logger.Info("Creating ConfigMap", "name", desired.Name)
			if err := r.Create(ctx, desired); err != nil {
				if k8serrors.IsAlreadyExists(err) {
					return nil // ConfigMap was created between Get and Create
				}
				return err
			}
			return nil
		}
		return err
	}

	// ConfigMap exists - update if content changed
	if existing.Data[resources.ContentKey] != *notebook.Spec.Content {
		logger.Info("Updating ConfigMap", "name", desired.Name)
		existing.Data = desired.Data
		if err := r.Update(ctx, existing); err != nil {
			return err
		}
	}

	return nil
}

func (r *MarimoNotebookReconciler) reconcilePVC(ctx context.Context, notebook *marimov1alpha1.MarimoNotebook) error {
	// Skip if no storage configured
	if notebook.Spec.Storage == nil {
		return nil
	}

	logger := logf.FromContext(ctx)
	desired := resources.BuildPVC(notebook)
	if desired == nil {
		return nil
	}

	// Set owner reference for automatic garbage collection
	if err := controllerutil.SetControllerReference(notebook, desired, r.Scheme); err != nil {
		return err
	}

	// Check if PVC exists
	existing := &corev1.PersistentVolumeClaim{}
	err := r.Get(ctx, client.ObjectKeyFromObject(desired), existing)
	if err != nil {
		if k8serrors.IsNotFound(err) {
			logger.Info("Creating PVC", "name", desired.Name, "size", desired.Spec.Resources.Requests.Storage().String())
			if err := r.Create(ctx, desired); err != nil {
				if k8serrors.IsAlreadyExists(err) {
					return nil // PVC was created between Get and Create
				}
				return err
			}
			return nil
		}
		return err
	}

	// PVC exists - we don't update PVCs (immutable size in most cases)
	return nil
}

func (r *MarimoNotebookReconciler) reconcilePod(ctx context.Context, notebook *marimov1alpha1.MarimoNotebook) (*corev1.Pod, error) {
	logger := logf.FromContext(ctx)
	desired := resources.BuildPod(notebook)

	// Set owner reference for automatic garbage collection
	if err := controllerutil.SetControllerReference(notebook, desired, r.Scheme); err != nil {
		return nil, err
	}

	// Check if Pod exists
	existing := &corev1.Pod{}
	err := r.Get(ctx, client.ObjectKeyFromObject(desired), existing)
	if err != nil {
		if k8serrors.IsNotFound(err) {
			logger.Info("Creating Pod", "name", desired.Name)
			if err := r.Create(ctx, desired); err != nil {
				if k8serrors.IsAlreadyExists(err) {
					// Pod was created between Get and Create, re-fetch
					if err := r.Get(ctx, client.ObjectKeyFromObject(desired), existing); err != nil {
						return nil, err
					}
					return existing, nil
				}
				return nil, err
			}
			return desired, nil
		}
		return nil, err
	}

	// Pod exists - we don't update running pods (recreate strategy)
	return existing, nil
}

func (r *MarimoNotebookReconciler) reconcileService(ctx context.Context, notebook *marimov1alpha1.MarimoNotebook) (*corev1.Service, error) {
	logger := logf.FromContext(ctx)
	desired := resources.BuildService(notebook)

	// Set owner reference
	if err := controllerutil.SetControllerReference(notebook, desired, r.Scheme); err != nil {
		return nil, err
	}

	// Check if Service exists
	existing := &corev1.Service{}
	err := r.Get(ctx, client.ObjectKeyFromObject(desired), existing)
	if err != nil {
		if k8serrors.IsNotFound(err) {
			logger.Info("Creating Service", "name", desired.Name)
			if err := r.Create(ctx, desired); err != nil {
				if k8serrors.IsAlreadyExists(err) {
					// Service was created between Get and Create, re-fetch
					if err := r.Get(ctx, client.ObjectKeyFromObject(desired), existing); err != nil {
						return nil, err
					}
					return existing, nil
				}
				return nil, err
			}
			return desired, nil
		}
		return nil, err
	}

	return existing, nil
}

func (r *MarimoNotebookReconciler) updateStatus(ctx context.Context, notebook *marimov1alpha1.MarimoNotebook, pod *corev1.Pod, svc *corev1.Service) (ctrl.Result, error) {
	// Determine phase from pod status
	phase := marimov1alpha1.PhasePending
	if pod != nil {
		switch pod.Status.Phase {
		case corev1.PodRunning:
			phase = marimov1alpha1.PhaseRunning
		case corev1.PodFailed:
			phase = marimov1alpha1.PhaseFailed
		}
	}

	// Build URL
	url := ""
	if svc != nil {
		url = fmt.Sprintf("http://%s.%s.svc.cluster.local:%d", svc.Name, svc.Namespace, notebook.Spec.Port)
	}

	// Compute content/source hash
	var sourceHash string
	if notebook.Spec.Content != nil {
		sourceHash = resources.ContentHash(*notebook.Spec.Content)
	} else {
		sourceHash = fmt.Sprintf("%x", sha256.Sum256([]byte(notebook.Spec.Source)))[:12]
	}

	// Get names safely
	podName := ""
	if pod != nil {
		podName = pod.Name
	}
	svcName := ""
	if svc != nil {
		svcName = svc.Name
	}

	// Update status if changed
	if notebook.Status.Phase != phase ||
		notebook.Status.URL != url ||
		notebook.Status.SourceHash != sourceHash ||
		notebook.Status.PodName != podName ||
		notebook.Status.ServiceName != svcName {

		notebook.Status.Phase = phase
		notebook.Status.URL = url
		notebook.Status.SourceHash = sourceHash
		notebook.Status.PodName = podName
		notebook.Status.ServiceName = svcName

		err := r.Status().Update(ctx, notebook)
		return ctrl.Result{}, err
	}

	return ctrl.Result{}, nil
}

// SetupWithManager sets up the controller with the Manager.
func (r *MarimoNotebookReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&marimov1alpha1.MarimoNotebook{}).
		Owns(&corev1.Pod{}).
		Owns(&corev1.Service{}).
		Owns(&corev1.PersistentVolumeClaim{}).
		Owns(&corev1.ConfigMap{}).
		Named("marimo").
		Complete(r)
}
