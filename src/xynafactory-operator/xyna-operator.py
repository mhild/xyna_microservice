import kopf

import kubernetes
from kubernetes import client
from kubernetes.client import Configuration
from kubernetes.client.rest import ApiException
from kubernetes import config
from kubernetes.stream import stream

import time
import logging
import os
import re

apps_v1 = kubernetes.client.AppsV1Api()
core_v1 = kubernetes.client.CoreV1Api()

# Configure Kubernetes Python client
#kubernetes.config.load_incluster_config()
#kubernetes.config.load_kube_config()
def load_k8s_config(logger):
    # Check if running inside a Kubernetes cluster
    logger.info(f'kubernetes service endpoint: {os.getenv("KUBERNETES_SERVICE_HOST")} / {os.getenv("KUBERNETES_SERVICE_PORT")}')
    if os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/token") and \
       os.getenv("KUBERNETES_SERVICE_HOST") and os.getenv("KUBERNETES_SERVICE_PORT"):
        config.load_incluster_config()
        logger.info("Loaded in-cluster config")
    else:
        config.load_kube_config()
        logger.info("Loaded local kubeconfig")

def wait_for_pods_ready(core_v1_api, namespace, label_selector, timeout=120, interval=5):
    end_time = time.time() + timeout

    while time.time() < end_time:
        pods = core_v1_api.list_namespaced_pod(namespace=namespace, label_selector=label_selector)
        all_ready = True

        for pod in pods.items:
            ready_condition = next((cond for cond in pod.status.conditions if cond.type == "Ready"), None)
            if not ready_condition or ready_condition.status != "True":
                all_ready = False
                break
            
            # If pod ready, exec command inside pod and check output
            exec_command = ["/bin/sh", "-c", "/opt/xyna/xyna_001/server/xynafactory.sh status"]  # Replace your command here
            resp = stream(core_v1_api.connect_get_namespaced_pod_exec,
                          pod.metadata.name,
                          namespace,
                          command=exec_command,
                          stderr=True,
                          stdin=False,
                          stdout=True,
                          tty=False)
            if "running" not in resp:
                all_ready = False
                break

        if all_ready and pods.items:
            return True
        time.sleep(interval)
    return False

def fetch_second_quote_content(s: str) -> str:
    # Find all text enclosed in single quotes
    matches = re.findall(r"'(.*?)'", s)
    # Return the second one if it exists
    return matches[1] if len(matches) > 1 else None

def to_dns_1035_label(s):
    # Lowercase
    s = s.lower()
    # Replace disallowed chars with dash
    s = re.sub(r'[^a-z0-9-]', '-', s)
    # Remove leading chars until a letter is found
    s = re.sub(r'^[^a-z]+', '', s)
    # Remove trailing chars until alphanumeric at end
    s = re.sub(r'[^a-z0-9]+$', '', s)
    # Truncate to max 63 chars
    if len(s) > 63:
        s = s[:63]
    # Fallback if empty
    if not s:
        s = 'default-name'
    return s

@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **kwargs):
    global core_v1, apps_v1
    settings.posting.level = logging.DEBUG
    logger = logging.getLogger(__name__)
    load_k8s_config(logger)

    configuration = Configuration.get_default_copy()

    # Create ApiClient with this configuration explicitly
    api_client = client.ApiClient(configuration=configuration)

    # Use this api_client for your API calls
    core_v1 = client.CoreV1Api(api_client=api_client)
    apps_v1 = client.AppsV1Api(api_client=api_client)

    logger.info("Cluster / Kubernetes service endpoint:")
    logger.info(f"Host: {configuration.host}")
    logger.info(f"SSL CA Cert: {configuration.ssl_ca_cert}")
    logger.info(f"API Key: {configuration.api_key}")



def exec_command_in_pod(namespace, pod_name, container_name, cmd, logger):
    """
    Execute a shell command in the specified pod container and return output.
    """

    logger.debug(f"executing command '{cmd}' in pod {pod_name}")

    resp = stream(core_v1.connect_get_namespaced_pod_exec,
                  pod_name,
                  namespace,
                  container=container_name,
                  command=cmd,
                  stderr=True,
                  stdin=False,
                  stdout=True,
                  tty=False)
    return resp

def make_service_object(serviceName, namespace, app_label, protocol, port, targetPort):
    metadata = client.V1ObjectMeta(
        name=serviceName,
        namespace=namespace,
        labels={"app": app_label}
    )
    ports = [client.V1ServicePort(
        protocol=protocol,
        port=port,
        target_port=targetPort
    )]
    spec = client.V1ServiceSpec(
        selector={"app": app_label},
        type="ClusterIP",
        ports=ports
    )
    service = client.V1Service(
        api_version="v1",
        kind="Service",
        metadata=metadata,
        spec=spec
    )
    return service

def get_service_manifest(cr_service_data, app_label, namespace, logger):


    defaultServiceName = f"service{ cr_service_data.get('port', '8080')}"
    serviceName = cr_service_data.get('serviceName', defaultServiceName)
    protocol = cr_service_data.get('protocol', 'TCP')
    port = cr_service_data.get('port', '8080')
    targetPort = cr_service_data.get('targetPort', '8080')

    return {'serviceName': serviceName, 'body': make_service_object(serviceName, namespace, app_label, protocol, port, targetPort)}


def make_deployment_object(name, namespace, replicas, image):
    metadata = client.V1ObjectMeta(name=f'{name}-deployment', namespace=namespace)
    labels = {"app": name}
    selector = client.V1LabelSelector(match_labels=labels)
    container = client.V1Container(
        name="xynafactory",
        image=image
    )
    pod_spec = client.V1PodSpec(containers=[container])
    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels=labels),
        spec=pod_spec
    )
    spec = client.V1DeploymentSpec(
        replicas=replicas,
        selector=selector,
        template=template
    )
    deployment = client.V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=metadata,
        spec=spec
    )
    return deployment

@kopf.on.create('xyna.com', 'v1alpha1', 'xynafactoryservices')
def on_create(spec, name, namespace, logger, **kwargs):

    logger.debug(f"creating deployment '{name}' in namespace {namespace}")

    image = spec.get("image", "xynafactory/xynafactory:latest")
    replicas = spec.get("replicas", 1)
    applications = spec.get("applications", [])
    servicePorts = spec.get("servicePorts", [])

    logger.debug(f"collecting {len(servicePorts)} service ports")
    services = [get_service_manifest(servicePort, name, namespace, logger) for servicePort in servicePorts]
    logger.debug(f"Applying deployments for services")
    for service in services:
        
        core_v1.create_namespaced_service(namespace=namespace, body=service['body'])
        logger.info(f"Created service {service['serviceName']} in namespace {namespace}")


    logger.debug(f"Preparing deployment manifest {name}")

    # Prepare deployment manifest dictionary
    # deployment_manifest = {
    #     "apiVersion": "apps/v1",
    #     "kind": "Deployment",
    #     "metadata": {"name": name, "namespace": namespace},
    #     "spec": {
    #         "replicas": replicas,
    #         "selector": {"matchLabels": {"app": name}},
    #         "template": {
    #             "metadata": {"labels": {"app": name}},
    #             "spec": {
    #                 "containers": [{
    #                     "name": "xynafactory",
    #                     "image": image
    #                 }]
    #             }
    #         }
    #     }
    # }

    deployment_manifest = make_deployment_object(name, namespace, replicas, image)

    # Create or update Deployment
    logger.debug(f"Applying deployment manifest {name}")
    try:
        apps_v1.create_namespaced_deployment(namespace=namespace, body=deployment_manifest)
        logger.info(f"Created Deployment {name}-deployment in namespace {namespace}")
    except ApiException as e:
        if e.status == 409:
            # Deployment already exists, update it
            apps_v1.replace_namespaced_deployment(f'{name}-deployment', namespace, deployment_manifest)
            logger.info(f"Updated Deployment {name}-deployment  in namespace {namespace}")
        else:
            raise

    # Optionally handle exec inside pod to import each application zip here
    # This requires listing pods with label app=name and running kubectl exec equivalents


    label_selector = f"app={name}"
    if wait_for_pods_ready(core_v1, namespace, label_selector):
    # Retrieve pods for this deployment (simplified: only first pod)
        pods = core_v1.list_namespaced_pod(namespace=namespace, label_selector=f"app={name}")
        if not pods.items:
            logger.info("No pods found yet, will requeue")
            return {'requeue': True}

        pod = pods.items[0]
        container_name = pod.spec.containers[0].name

        for app in applications:
            zip_url = app.get("appUrl")
            app_name = app.get("name")
            zip_name = zip_url.split("/")[-1]

            # Download the zip inside the pod and run import CLI command
            download_cmd = ['curl', '-o', f'/tmp/{zip_name}', zip_url]
            logger.info(f"Downloading {zip_url} (application '{app_name}') inside pod {pod.metadata.name}")
            output = exec_command_in_pod(namespace, pod.metadata.name, container_name, download_cmd, logger)
            logger.info(f"Download output: {output}")

            import_cmd = ['/opt/xyna/xyna_001/server/xynafactory.sh', 'importapplication', '-filename', f'/tmp/{zip_name}']
            logger.info(f"Importing file {zip_name} in pod {pod.metadata.name}")
            output = exec_command_in_pod(namespace, pod.metadata.name, container_name, import_cmd, logger)
            logger.info(f"Import output: {output}")

            # get version
            app_info_cmd = ["/bin/sh", "-c", f"/opt/xyna/xyna_001/server/xynafactory.sh listapplications | grep {app_name}"]
            logger.info(f"Getting app-info for {app_name} in pod {pod.metadata.name}")
            output = exec_command_in_pod(namespace, pod.metadata.name, container_name, app_info_cmd, logger)
            logger.info(f"App info output: {output}")
            version_str = fetch_second_quote_content(output)

            start_cmd = ['/opt/xyna/xyna_001/server/xynafactory.sh', 'startapplication', '-applicationName', f'"{app_name}"', '-versionName', f'"{version_str}"']
            logger.info(f"Starting app {app_name} in pod {pod.metadata.name}")
            output = exec_command_in_pod(namespace, pod.metadata.name, container_name, start_cmd, logger)
            logger.info(f"Start output: {output}")

    else:
        # Timeout or pod not ready, handle accordingly
        logger.error(f"Failed to finish deployment {name}, pod didn't get ready: {str(e)}")



@kopf.on.update('xyna.com', 'v1alpha1', 'xynafactoryservices')
def on_update(spec, name, namespace, logger, **kwargs):
    # Similar to on_create, possibly update deployment or re-import apps
    logger.info(f"Received update for {name} in {namespace}")
    desired_replicas = spec.get('replicas', 1)

    # Patch the deployment's replicas count to desired_replicas
    patch = {'spec': {'replicas': desired_replicas}}
    apps_v1.patch_namespaced_deployment(name + '-deployment', namespace, patch)
    logger.info(f"Scaled deployment {name}-deployment to {desired_replicas} replicas")


@kopf.on.delete('xyna.com', 'v1alpha1', 'xynafactoryservices')
def on_delete(spec, name, namespace, logger, **kwargs):

    # Cleanup deployment or related resources
    try:
        apps_v1.delete_namespaced_deployment(name, namespace)
        logger.info(f"Deleted deployment {name} in {namespace}")
    except ApiException as e:
        logger.error(f"Failed to delete deployment {name}: {str(e)}")


    servicePorts = spec.get("servicePorts", [])
    for service in servicePorts:
        try:
            core_v1.delete_namespaced_service(service['serviceName'], namespace)
            logger.info(f"Deleted service {service['serviceName']} in {namespace}")
        except ApiException as e:
            logger.error(f"Failed to delete service {service['serviceName']}: {str(e)}")  