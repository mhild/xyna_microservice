> [!CAUTION]
> This is a proof-of-concept - not production-ready
> - the os architecture is limited to amd64/x86 (arm64 like apple silicon or Raspberry Pi is not supported)


# Xyna Microservice Environment in Kubernetes
This helm chart imports a Custom Resource Definition "XynaFactoryService" in an kubernetes cluster.

The XynaFactoryService allows to describe a Xyna Microservice by
1. xyna-factory image tag
2. defining XynaApplications to be imported (it has to be available via URL by the cluster)
3. service port(s) and respective target ports on the pods

Such a XynaFactoryService manifest applied via kubectl will then:
-  pull xynafactory image and start it as a pod
-  import and start the defined XynaApplications (currently it is not taken care of dependencies)
-  create services as defined in the manifest 

The manifest for the ingress is not yet created automatically.  

   
## Prerequisites
* Kubernetes Environment is setup (Docker Desktop, k3s,...)
* helm ( https://helm.sh/) is installed
* For external accessibility of the service an ingress controller like Traefik or nginx is required:
    ```bash
    helm repo add traefik https://traefik.github.io/charts
    helm repo update
    helm install traefik traefik/traefik --wait --set ingressRoute.dashboard.enabled=true --set ingressRoute.dashboard.matchRule='Host(`dashboard.localhost`)'  --set ingressRoute.dashboard.entryPoints={web} --set providers.kubernetesGateway.enabled=true --set gateway.listeners.web.namespacePolicy.from=All
    ```
    This makes the Traefik dashboard available at http://dashboard.localhost/dashboard/ .
## Create namespace
Create a namespace in kubernetes
```bash
kubectl create namespace xyna
```
In this example the namespace 'xyna' is created, but the name is arbitrary in general.

### Add help repo
#### Use existing development repo on github
```bash
 helm repo add mhild.github.io https://mhild.github.io/xyna_microservice/helm_repository/
 helm repo update
 helm install xynafactory-operator mhild.github.io/xynafactory-operator --version 0.1.2 -n xyna
```

Alternatiely, a local repository can be used; here hosted by simple http-server:
Checkout the repository or put contents of folder 'helm_repository' in the filsystem.
Change in to the folder and package/index charts:
```bash
helm package ./xynafactory-operator
helm repo index . --url http://localhost:8888
````

Start http-server in folder. Here, the python module http.server is used:
```bash
python -m http.server 8888
````

The local repository is added as shon above:
```bash
 helm repo add local_helm_repo http://localhost:8888/
````

After installation of the helm chart, the cluster has the Custom Resource Definition 'XynaFactoryService'.
## Import Xyna Microservice CRD in Kubernetes

### Requirements:
- a Xyna-Application (or a bundle of Apps), which form the microservice
- all Xyna-Applications must be available via an URL (Note: the webserver cannot listen on localhost, since the pods must access it. A LAN IP, however, should work fine).
  - A simple Hello-World application is available in folder 'example_microservice/app_repo/ello_microservice_0.1.app' and accessible via URL https://mhild.github.io/xyna_microservice/example_microservice/app_repo/hello_microservice_0.1.app .
 
> [!CAUTION]
> All dependent applications have to be defined and accessible by an URL. This is also true for xyna standard modules, that do not come with the factory-image.
> In case of dependencies between applications, the order of import must be defined via the property 'order' in the applications-section below. Otherwise, the service wil fail.

### Create a resource XynaFactoryService

An example microservice based on aboves application:

File ```hello_microservice.yaml```:
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
      appUrl: "https://mhild.github.io/xyna_microservice/example_microservice/app_repo/hello_microservice_0.1.app"
  servicePorts:
    - serviceName: hello-microservice
      port: 8001
      targetPort: 8001
      protocol: TCP
```

Important properties are:
 - spec.image -> image of xynafactory which is used as runtime engine for the applications(s)
 - replicas -> no. of pods created
 - applications: list of applications imported into the microservice
   - name: exact name of the xyna application
   - order: in case of multiple applications 'order' defines the order of app import to take care of dependencies. Lower numbers are imported first. Applications without 'order' are imported at the end in arbitrary order.
   - appUrl: URL to the application-package - must be accessible from inside the cluster.
 - servicePorts -> List of ports exposed in the cluster; typically, these are the endpoints of triggers in one or more of the applications
   - serviceName: name of the service. Must be dns_1035 conform (no underscore) 
   - port: port exposed by the service
   - targetPort: port, the pods listen on (i.e., port of an trigger exposed by the applications)
   - protocol: TCP|UDP - default is TCP

Deployment of the microservice:
```bash
kubectl  apply -n xyna -f ./hello_microservice.yaml
```

After approx. 25-30s the service should be ready.

In order to access the service externaly, an ingress manifest for each service has to be applied:

File ```microservice-ingress.yaml```:
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

This manifest requires traefik as ingress controller. With running
```bash
kubectl apply -n xyna -f microservice-ingress.yaml
```
the service is available at URL http://xyna.localhost/hello

## Scaling the service
Changing the number of replicas (i.e., to 3) is done by patching the resource:

```bash
kubectl patch XynaFactoryService hello-microservice-app-service -n xyna --type merge -p '{\"spec\": {\"replicas\": 3}}'
```
