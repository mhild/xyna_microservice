
# Quickstart Guide

This guide walks you through setting up the **Xyna Microservice Environment** in Kubernetes using the Helm operator and the example Hello World microservice.

---

## 1. Prerequisites

- A running **Kubernetes cluster** (tested: Docker Desktop, k3s).  
- **Helm** installed ([https://helm.sh](https://helm.sh/)).  
- **Ingress controller** installed (Traefik or NGINX).  

Optional: enable the Traefik dashboard for monitoring (example in the main README).

---

## 2. Install the Operator

Create a namespace:

```bash
kubectl create namespace xyna
```

Add Helm repository with operator chart:

```bash
helm repo add mhild.github.io https://mhild.github.io/xyna_microservice/helm_repository/
helm repo update
helm install xynafactory-operator mhild.github.io/xynafactory-operator --version 0.1.2 -n xyna
````


---

## 3. Deploy Example Microservice

Apply the example resource:

```bash
kubectl apply -n xyna -f https://mhild.github.io/xyna_microservice/example_microservice/hello_microservice.yaml
````

Wait ~25–30 seconds until the pod and service are ready.

---

## 4. Configure Ingress

Apply the example ingress:

```bash
kubectl apply -n xyna -f https://mhild.github.io/xyna_microservice/example_microservice/microservice-ingress.yaml
````


The Hello World service is now accessible at:  
[http://xyna.localhost/hello](http://xyna.localhost/hello)

---

## 5. Scaling

To scale to 3 replicas:

```bash
kubectl patch XynaFactoryService hello-microservice-app-service
-n xyna --type merge -p '{"spec": {"replicas": 3}}'
````


---

✅ Congratulations! You have successfully deployed a Xyna Microservice using the custom operator.
