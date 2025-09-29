# Troubleshooting Guide

This document lists common problems and their solutions when working with the Xyna Microservice Environment.

---

## Problem: Pods stuck in `ImagePullBackOff`

**Cause:** The cluster cannot fetch the specified image (e.g., typo in `spec.image`, missing registry login).  
**Solution:**  
- Verify the `spec.image` field in your `XynaFactoryService`.  
- Make sure the image is publicly available or configure image pull secrets.  

---

## Problem: Applications fail to start due to missing dependencies

**Cause:** Applications have dependencies, but import order was not defined.  
**Solution:**  
- In the CR YAML, set the `order` property for each application.  
- Define lower numbers for dependencies that must load first.  

---

## Problem: Service not reachable from browser

**Cause:** No ingress manifest was applied, or Ingress controller not installed.  
**Solution:**  
- Verify that Traefik or NGINX ingress controller is running.  
- Apply the `microservice-ingress.yaml` example.  
- Check DNS resolution for the `host` field (e.g., add `xyna.localhost` entry to `/etc/hosts` if needed).  

---

## Problem: Connection refused on service port

**Cause:** The configured `servicePorts` values (port/targetPort) are incorrect.  
**Solution:**  
- Make sure the port in the application (trigger) matches the service definition.  
- Check pod logs to confirm which port the application exposes.  

---

## Problem: `kubectl apply` fails due to "no matches for kind XynaFactoryService"

**Cause:** CRD not installed yet.  
**Solution:**  
- Ensure the Helm chart for `xynafactory-operator` was installed successfully.  
- Verify with `kubectl get crd | grep xyna`.  

---

## Problem: Ingress returns 404

**Cause:** Path or service name mismatch in ingress manifest.  
**Solution:**  
- Double-check that the `serviceName` in ingress maps exactly to the `serviceName` in your `XynaFactoryService`.  
- Confirm `pathType` is set to `Prefix`.  
