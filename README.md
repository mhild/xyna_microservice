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

### Add help repo
```bash
 helm repo add mhild.github.io https://mhild.github.io/xyna_microservice/helm_repository/
```
## Import Xyna Microservice CRD in Kubernetes


