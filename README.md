# Xyna Microservice Environment on Kubernetes

> [!CAUTION]
> This project is a **proof of concept** – not production-ready.  
> - Supported OS Architectures: **amd64/x86 only** (ARM64 platforms like Apple Silicon or Raspberry Pi are not supported).  
> - Tested environment: **Kubernetes on Docker Desktop (Windows 11)**. Steps should also work on other platforms (e.g., *k3s*).  

---

## 🚀 Quickstart (TL;DR)

1. Create namespace
kubectl create namespace xyna

2. Add Helm repository and install Xyna Operator
helm repo add mhild.github.io https://mhild.github.io/xyna_microservice/helm_repository/
helm repo update
helm install xynafactory-operator mhild.github.io/xynafactory-operator --version 0.1.2 -n xyna

3. Deploy Hello World microservice
kubectl apply -n xyna -f https://mhild.github.io/xyna_microservice/example_microservice/hello_microservice.yaml

4. Install ingress manifest (example for Traefik)
kubectl apply -n xyna -f https://mhild.github.io/xyna_microservice/example_microservice/microservice-ingress.yaml

5. Access the microservice
http://xyna.localhost/hello


For details, see sections below.

---

## Overview

The Helm chart deploys the **XynaFactoryService** CRD and Operator.  
A `XynaFactoryService` resource allows you to:

1. Define the **XynaFactory container image** to run.  
2. Import one or more **Xyna Applications** (packaged and available via URL).  
3. Expose services at specific **ports** inside the cluster.  

When applied, the CR:  
- Pulls and starts the given Xyna Factory image.  
- Imports the listed Xyna Applications (import order must be specified manually).  
- Creates Kubernetes Services for the defined ports.  

Ingress manifests are **not generated automatically** and must be added manually.

---

## Prerequisites

- A running **Kubernetes cluster** (e.g., Docker Desktop, k3s).  
- **Helm** installed ([https://helm.sh](https://helm.sh/)).  
- An **Ingress controller** such as *Traefik* or *NGINX* if you want external access.  

Example: install Traefik ingress controller  

    ```bash
    helm repo add traefik https://traefik.github.io/charts
    helm repo update
    helm install traefik traefik/traefik --wait --set ingressRoute.dashboard.enabled=true --set ingressRoute.dashboard.matchRule='Host(`dashboard.localhost`)'  --set ingressRoute.dashboard.entryPoints={web} --set providers.kubernetesGateway.enabled=true --set gateway.listeners.web.namespacePolicy.from=All
    ```
  

---

## Installation

### 1. Create a namespace

```bash
kubectl create namespace xyna
```

### 2. Install the CRD and Operator

#### Using the public Helm repository

```bash
 helm repo add mhild.github.io https://mhild.github.io/xyna_microservice/helm_repository/
 helm repo update
 helm install xynafactory-operator mhild.github.io/xynafactory-operator --version 0.1.2 -n xyna
```


#### Using a local Helm repository (development)

```bash
helm package ./xynafactory-operator
helm repo index . --url http://localhost:8888

helm repo add local_helm_repo http://localhost:8888/
```

The local repository is added as shon above:
```bash
 helm repo add local_helm_repo http://localhost:8888/
````


---

## Deploying a Xyna Microservice

### Requirements
- At least one **Xyna Application** (or bundle).  
- Applications must be downloadable via URL (reachable from inside the cluster).  

Example Hello World application:  
[hello_microservice_0.2.app](https://mhild.github.io/xyna_microservice/example_microservice/app_repo/hello_microservice_0.2.app)  

> [!CAUTION]
> - All dependent applications must also be declared and accessible by URL.  
> - Dependencies must be ordered manually using the `order` property.  

---

### Example Manifest: `hello_microservice.yaml`


```yaml
apiVersion: xyna.com/v1alpha1
kind: XynaFactoryService
metadata:
  name: hello-microservice-app-service
spec:
  image: "xynafactory/factory:latest"
  replicas: 1
  applications:
    - name: hello_microservice
      order: 1
      appUrl: "https://mhild.github.io/xyna_microservice/example_microservice/app_repo/hello_microservice_0.2.app"
  servicePorts:
    - serviceName: hello-microservice
      port: 8001
      targetPort: 8001
      protocol: TCP
```


**Key Properties**  
- `image`: Xyna Factory runtime image.  
- `replicas`: Number of pods to run.  
- `applications`: List of imported apps.  
  - `order`: Controls import sequence.  
  - `appUrl`: Must be reachable inside the cluster.  
- `servicePorts`: Exposed endpoints in the cluster.  
  - `serviceName`: Must be DNS-1035 compliant (no underscores).  
  - `port`: Exposed service port.  
  - `targetPort`: Trigger port inside the container.  
  - `protocol`: Default is TCP.  

Apply the manifest:


```bash
kubectl  apply -n xyna -f ./hello_microservice.yaml
```


After ~25–30s the service should be ready.

---

### Exposing the Service Externally

Create `microservice-ingress.yaml`:  


```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: hello-ingress
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: web
spec:
  rules:
  - host: xyna.localhost
    http:
      paths:
      - path: /hello
        pathType: Prefix
        backend:
          service:
            name: hello-microservice
            port:
              number: 8001
```


Apply it:  


```bash
kubectl apply -n xyna -f microservice-ingress.yaml
```

Now the service can be accessed at:  
[http://xyna.localhost/hello](http://xyna.localhost/hello)  

---

## Scaling

Increase replicas by patching the CR:


```bash
kubectl patch XynaFactoryService hello-microservice-app-service -n xyna --type merge -p '{\"spec\": {\"replicas\": 3}}'
```


---

## Known Limitations

- **No automated dependency management** for applications.  
- **Ingress manifests must be created manually**.  
- **Namespace defaults**: All examples use `xyna`. If you use another namespace, ensure all commands and manifests are updated.  

---
