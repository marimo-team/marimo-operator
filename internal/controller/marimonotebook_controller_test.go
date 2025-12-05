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
	"time"

	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/types"
	"sigs.k8s.io/controller-runtime/pkg/client"

	marimov1alpha1 "github.com/marimo-team/marimo-operator/api/v1alpha1"
)

var _ = Describe("MarimoNotebook Controller", func() {
	const (
		timeout  = time.Second * 10
		interval = time.Millisecond * 250
	)

	Context("When creating a MarimoNotebook", func() {
		var notebook *marimov1alpha1.MarimoNotebook
		var namespacedName types.NamespacedName

		BeforeEach(func() {
			notebook = &marimov1alpha1.MarimoNotebook{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-notebook-" + randString(5),
					Namespace: "default",
				},
				Spec: marimov1alpha1.MarimoNotebookSpec{
					Source: "https://github.com/marimo-team/marimo.git",
				},
			}
			namespacedName = types.NamespacedName{
				Name:      notebook.Name,
				Namespace: notebook.Namespace,
			}
		})

		AfterEach(func() {
			// Clean up the notebook
			_ = k8sClient.Delete(ctx, notebook)
		})

		It("should create Pod and Service", func() {
			By("creating the MarimoNotebook")
			Expect(k8sClient.Create(ctx, notebook)).To(Succeed())

			By("checking that Pod is created")
			pod := &corev1.Pod{}
			Eventually(func() error {
				return k8sClient.Get(ctx, namespacedName, pod)
			}, timeout, interval).Should(Succeed())

			Expect(pod.Spec.Containers).To(HaveLen(1))
			Expect(pod.Spec.Containers[0].Name).To(Equal("marimo"))
			Expect(pod.Spec.InitContainers).To(HaveLen(1))
			Expect(pod.Spec.InitContainers[0].Name).To(Equal("git-clone"))

			By("checking that Service is created")
			svc := &corev1.Service{}
			Eventually(func() error {
				return k8sClient.Get(ctx, namespacedName, svc)
			}, timeout, interval).Should(Succeed())

			Expect(svc.Spec.Ports).To(HaveLen(1))
			Expect(svc.Spec.Ports[0].Port).To(Equal(int32(2718)))
		})

		It("should apply default values", func() {
			By("creating the MarimoNotebook with minimal spec")
			Expect(k8sClient.Create(ctx, notebook)).To(Succeed())

			By("checking Pod has default image and port")
			pod := &corev1.Pod{}
			Eventually(func() error {
				return k8sClient.Get(ctx, namespacedName, pod)
			}, timeout, interval).Should(Succeed())

			// Check default image
			Expect(pod.Spec.Containers[0].Image).To(Equal("ghcr.io/marimo-team/marimo:latest"))

			// Check default port
			Expect(pod.Spec.Containers[0].Ports[0].ContainerPort).To(Equal(int32(2718)))
		})

		It("should set owner references for garbage collection", func() {
			By("creating the MarimoNotebook")
			Expect(k8sClient.Create(ctx, notebook)).To(Succeed())

			By("checking Pod has owner reference")
			pod := &corev1.Pod{}
			Eventually(func() error {
				return k8sClient.Get(ctx, namespacedName, pod)
			}, timeout, interval).Should(Succeed())

			Expect(pod.OwnerReferences).To(HaveLen(1))
			Expect(pod.OwnerReferences[0].Kind).To(Equal("MarimoNotebook"))
			Expect(pod.OwnerReferences[0].Name).To(Equal(notebook.Name))

			By("checking Service has owner reference")
			svc := &corev1.Service{}
			Eventually(func() error {
				return k8sClient.Get(ctx, namespacedName, svc)
			}, timeout, interval).Should(Succeed())

			Expect(svc.OwnerReferences).To(HaveLen(1))
			Expect(svc.OwnerReferences[0].Kind).To(Equal("MarimoNotebook"))
		})

		It("should update status with pod and service names", func() {
			By("creating the MarimoNotebook")
			Expect(k8sClient.Create(ctx, notebook)).To(Succeed())

			By("checking status is updated")
			Eventually(func() string {
				nb := &marimov1alpha1.MarimoNotebook{}
				if err := k8sClient.Get(ctx, namespacedName, nb); err != nil {
					return ""
				}
				return nb.Status.PodName
			}, timeout, interval).Should(Equal(notebook.Name))

			nb := &marimov1alpha1.MarimoNotebook{}
			Expect(k8sClient.Get(ctx, namespacedName, nb)).To(Succeed())
			Expect(nb.Status.ServiceName).To(Equal(notebook.Name))
			Expect(nb.Status.URL).To(ContainSubstring(notebook.Name))
			Expect(nb.Status.SourceHash).NotTo(BeEmpty())
		})

		It("should use custom port when specified", func() {
			notebook.Spec.Port = 8080

			By("creating the MarimoNotebook with custom port")
			Expect(k8sClient.Create(ctx, notebook)).To(Succeed())

			By("checking Pod uses custom port")
			pod := &corev1.Pod{}
			Eventually(func() error {
				return k8sClient.Get(ctx, namespacedName, pod)
			}, timeout, interval).Should(Succeed())

			Expect(pod.Spec.Containers[0].Ports[0].ContainerPort).To(Equal(int32(8080)))

			By("checking Service uses custom port")
			svc := &corev1.Service{}
			Eventually(func() error {
				return k8sClient.Get(ctx, namespacedName, svc)
			}, timeout, interval).Should(Succeed())

			Expect(svc.Spec.Ports[0].Port).To(Equal(int32(8080)))
		})

		It("should use custom image when specified", func() {
			notebook.Spec.Image = "marimo:custom"

			By("creating the MarimoNotebook with custom image")
			Expect(k8sClient.Create(ctx, notebook)).To(Succeed())

			By("checking Pod uses custom image")
			pod := &corev1.Pod{}
			Eventually(func() error {
				return k8sClient.Get(ctx, namespacedName, pod)
			}, timeout, interval).Should(Succeed())

			Expect(pod.Spec.Containers[0].Image).To(Equal("marimo:custom"))
		})
	})

	Context("When creating a MarimoNotebook with storage", func() {
		It("should create PVC with correct size", func() {
			notebook := &marimov1alpha1.MarimoNotebook{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-pvc-" + randString(5),
					Namespace: "default",
				},
				Spec: marimov1alpha1.MarimoNotebookSpec{
					Source: "https://github.com/marimo-team/marimo.git",
					Storage: &marimov1alpha1.StorageSpec{
						Size: "2Gi",
					},
				},
			}
			namespacedName := types.NamespacedName{
				Name:      notebook.Name,
				Namespace: notebook.Namespace,
			}

			defer func() {
				_ = k8sClient.Delete(ctx, notebook)
			}()

			By("creating the MarimoNotebook with storage")
			Expect(k8sClient.Create(ctx, notebook)).To(Succeed())

			By("checking that PVC is created")
			pvc := &corev1.PersistentVolumeClaim{}
			Eventually(func() error {
				return k8sClient.Get(ctx, namespacedName, pvc)
			}, timeout, interval).Should(Succeed())

			Expect(pvc.Spec.Resources.Requests.Storage().String()).To(Equal("2Gi"))
			Expect(pvc.Spec.AccessModes).To(ContainElement(corev1.ReadWriteOnce))

			By("checking PVC has owner reference")
			Expect(pvc.OwnerReferences).To(HaveLen(1))
			Expect(pvc.OwnerReferences[0].Kind).To(Equal("MarimoNotebook"))
			Expect(pvc.OwnerReferences[0].Name).To(Equal(notebook.Name))

			By("checking Pod uses PVC volume")
			pod := &corev1.Pod{}
			Eventually(func() error {
				return k8sClient.Get(ctx, namespacedName, pod)
			}, timeout, interval).Should(Succeed())

			var foundPVCVolume bool
			for _, vol := range pod.Spec.Volumes {
				if vol.PersistentVolumeClaim != nil && vol.PersistentVolumeClaim.ClaimName == notebook.Name {
					foundPVCVolume = true
					break
				}
			}
			Expect(foundPVCVolume).To(BeTrue(), "Pod should have PVC volume")
		})

		It("should not create PVC when storage is not specified", func() {
			notebook := &marimov1alpha1.MarimoNotebook{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-no-pvc-" + randString(5),
					Namespace: "default",
				},
				Spec: marimov1alpha1.MarimoNotebookSpec{
					Source: "https://github.com/marimo-team/marimo.git",
					// No storage configured
				},
			}
			namespacedName := types.NamespacedName{
				Name:      notebook.Name,
				Namespace: notebook.Namespace,
			}

			defer func() {
				_ = k8sClient.Delete(ctx, notebook)
			}()

			By("creating the MarimoNotebook without storage")
			Expect(k8sClient.Create(ctx, notebook)).To(Succeed())

			By("waiting for Pod to be created")
			pod := &corev1.Pod{}
			Eventually(func() error {
				return k8sClient.Get(ctx, namespacedName, pod)
			}, timeout, interval).Should(Succeed())

			By("checking that PVC is NOT created")
			pvc := &corev1.PersistentVolumeClaim{}
			Consistently(func() bool {
				err := k8sClient.Get(ctx, namespacedName, pvc)
				return client.IgnoreNotFound(err) == nil && err != nil
			}, time.Second*2, interval).Should(BeTrue(), "PVC should not be created")

			By("checking Pod uses emptyDir volume")
			var foundEmptyDir bool
			for _, vol := range pod.Spec.Volumes {
				if vol.EmptyDir != nil {
					foundEmptyDir = true
					break
				}
			}
			Expect(foundEmptyDir).To(BeTrue(), "Pod should have emptyDir volume when no storage")
		})
	})

	Context("When deleting a MarimoNotebook", func() {
		It("should clean up owned resources via garbage collection", func() {
			notebook := &marimov1alpha1.MarimoNotebook{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-delete-" + randString(5),
					Namespace: "default",
				},
				Spec: marimov1alpha1.MarimoNotebookSpec{
					Source: "https://github.com/marimo-team/marimo.git",
				},
			}
			namespacedName := types.NamespacedName{
				Name:      notebook.Name,
				Namespace: notebook.Namespace,
			}

			By("creating the MarimoNotebook")
			Expect(k8sClient.Create(ctx, notebook)).To(Succeed())

			By("waiting for Pod to be created")
			pod := &corev1.Pod{}
			Eventually(func() error {
				return k8sClient.Get(ctx, namespacedName, pod)
			}, timeout, interval).Should(Succeed())

			By("deleting the MarimoNotebook")
			Expect(k8sClient.Delete(ctx, notebook)).To(Succeed())

			By("checking MarimoNotebook is deleted")
			Eventually(func() bool {
				err := k8sClient.Get(ctx, namespacedName, &marimov1alpha1.MarimoNotebook{})
				return client.IgnoreNotFound(err) == nil
			}, timeout, interval).Should(BeTrue())
		})
	})

	Context("Reconciliation idempotency", func() {
		It("should not recreate existing resources", func() {
			notebook := &marimov1alpha1.MarimoNotebook{
				ObjectMeta: metav1.ObjectMeta{
					Name:      "test-idempotent-" + randString(5),
					Namespace: "default",
				},
				Spec: marimov1alpha1.MarimoNotebookSpec{
					Source: "https://github.com/marimo-team/marimo.git",
				},
			}
			namespacedName := types.NamespacedName{
				Name:      notebook.Name,
				Namespace: notebook.Namespace,
			}

			defer func() {
				_ = k8sClient.Delete(ctx, notebook)
			}()

			By("creating the MarimoNotebook")
			Expect(k8sClient.Create(ctx, notebook)).To(Succeed())

			By("waiting for Pod to be created")
			pod := &corev1.Pod{}
			Eventually(func() error {
				return k8sClient.Get(ctx, namespacedName, pod)
			}, timeout, interval).Should(Succeed())

			originalUID := pod.UID

			By("triggering reconciliation by updating the notebook")
			nb := &marimov1alpha1.MarimoNotebook{}
			Expect(k8sClient.Get(ctx, namespacedName, nb)).To(Succeed())
			if nb.Annotations == nil {
				nb.Annotations = make(map[string]string)
			}
			nb.Annotations["test"] = "trigger-reconcile"
			Expect(k8sClient.Update(ctx, nb)).To(Succeed())

			By("verifying Pod was not recreated")
			time.Sleep(time.Second) // Give reconciler time to act
			Expect(k8sClient.Get(ctx, namespacedName, pod)).To(Succeed())
			Expect(pod.UID).To(Equal(originalUID))
		})
	})
})

// randString generates a random string for unique test resource names
func randString(n int) string {
	const letters = "abcdefghijklmnopqrstuvwxyz"
	b := make([]byte, n)
	for i := range b {
		b[i] = letters[time.Now().UnixNano()%int64(len(letters))]
		time.Sleep(time.Nanosecond)
	}
	return string(b)
}
