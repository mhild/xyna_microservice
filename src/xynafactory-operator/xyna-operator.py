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
# kubernetes.config.load_incluster_config()
# kubernetes.config.load_kube_config()
def load_k8s_config(logger):
    # Check if running inside a Kubernetes cluster
    logger.info(
        f'kubernetes service endpoint: {os.getenv("KUBERNETES_SERVICE_HOST")} / {os.getenv("KUBERNETES_SERVICE_PORT")}'
    )
    if (
        os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/token")
        and os.getenv("KUBERNETES_SERVICE_HOST")
        and os.getenv("KUBERNETES_SERVICE_PORT")
    ):
        config.load_incluster_config()
        logger.info("Loaded in-cluster config")
    else:
        config.load_kube_config()
        logger.info("Loaded local kubeconfig")


def wait_for_pods_ready(
    core_v1_api, namespace, label_selector, timeout=120, interval=5
):
    end_time = time.time() + timeout

    while time.time() < end_time:
        pods = core_v1_api.list_namespaced_pod(
            namespace=namespace, label_selector=label_selector
        )
        all_ready = True

        for pod in pods.items:
            # ready_condition = next((cond for cond in pod.status.conditions if cond.type == "Ready"), None)
            # if not ready_condition or ready_condition.status != "True":
            #     all_ready = False
            #     break

            # If pod ready, exec command inside pod and check output
            exec_command = [
                "/bin/sh",
                "-c",
                "/opt/xyna/xyna_001/server/xynafactory.sh status",
            ]  # Replace your command here
            resp = None
            try:
                resp = stream(
                    core_v1_api.connect_get_namespaced_pod_exec,
                    pod.metadata.name,
                    namespace,
                    command=exec_command,
                    stderr=True,
                    stdin=False,
                    stdout=True,
                    tty=False,
                )
            except Exception:
                all_ready = False
                break

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
    s = re.sub(r"[^a-z0-9-]", "-", s)
    # Remove leading chars until a letter is found
    s = re.sub(r"^[^a-z]+", "", s)
    # Remove trailing chars until alphanumeric at end
    s = re.sub(r"[^a-z0-9]+$", "", s)
    # Truncate to max 63 chars
    if len(s) > 63:
        s = s[:63]
    # Fallback if empty
    if not s:
        s = "default-name"
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

    resp = stream(
        core_v1.connect_get_namespaced_pod_exec,
        pod_name,
        namespace,
        container=container_name,
        command=cmd,
        stderr=True,
        stdin=False,
        stdout=True,
        tty=False,
    )
    return resp


def make_service_object(serviceName, namespace, app_label, protocol, port, targetPort):
    metadata = client.V1ObjectMeta(
        name=serviceName, namespace=namespace, labels={"app": app_label}
    )
    ports = [client.V1ServicePort(protocol=protocol, port=port, target_port=targetPort)]
    spec = client.V1ServiceSpec(
        selector={"app": app_label}, type="ClusterIP", ports=ports
    )
    service = client.V1Service(
        api_version="v1", kind="Service", metadata=metadata, spec=spec
    )
    return service


# helper: scans servicePorts for possible livenessProbes of the pod
# if a TCP port is found, its port is used as porbe - first port wins
def get_tcp_port_for_probe(servicePorts) -> int:
    for servicePort in servicePorts:
        if servicePort.get("protocol", "TCP") == "TCP":
            return int(servicePort.get("targetPort", "8080"))


# create service manifests
# takes an item of servicePorts from CRD
# creates a service for each port
def get_service_manifest(cr_service_data, app_label, namespace, logger):

    defaultServiceName = f"service{ cr_service_data.get('port', '8080')}"
    serviceName = cr_service_data.get("serviceName", defaultServiceName)
    protocol = cr_service_data.get("protocol", "TCP")
    port = cr_service_data.get("port", "8080")
    targetPort = cr_service_data.get("targetPort", "8080")

    return {
        "serviceName": serviceName,
        "body": make_service_object(
            serviceName, namespace, app_label, protocol, port, targetPort
        ),
    }


# create deployment maniifest
def make_deployment_object(
    name,
    namespace,
    replicas,
    image,
    nodeLabels = None,
    tcpPort: int = None,
    initialDelaySeconds: int = 20,
    periodSeconds: int = 10,
    timeoutSeconds: int = 1,
    failureThreshold: int = 10,
    successThreshold: int = 1,
):
    metadata = client.V1ObjectMeta(name=f"{name}-deployment", namespace=namespace)
    labels = {"app": name}
    selector = client.V1LabelSelector(match_labels=labels)

    readiness_probe = None
    if tcpPort is not None:
        readiness_probe = client.V1Probe(
            tcp_socket=client.V1TCPSocketAction(port=tcpPort),
            initial_delay_seconds=initialDelaySeconds,
            period_seconds=periodSeconds,
            timeout_seconds=timeoutSeconds,
            failure_threshold=failureThreshold,
            success_threshold=successThreshold,
        )

    container = client.V1Container(
        name="xynafactory", image=image, readiness_probe=readiness_probe
    )

    # nodeAffinity
    # Build nodeAffinity requiredDuringSchedulingIgnoredDuringExecution
    affinity = None
    if nodeLabels is not None:
        match_expressions = []
        for label in nodeLabels:
            match_expressions.append(
                client.V1NodeSelectorRequirement(
                    key=label["key"], operator="In", values=[label["value"]]
                )
            )

        node_selector_term = client.V1NodeSelectorTerm(match_expressions=match_expressions)
        node_affinity = client.V1NodeAffinity(
            required_during_scheduling_ignored_during_execution=client.V1NodeSelector(
                node_selector_terms=[node_selector_term]
            )
        )
        affinity = client.V1Affinity(node_affinity=node_affinity)

    # Workaround: it seems, that if there is no node_affinity client.V1PodSpec() should be called
    # without the "affinity=" argument. Otherwise, there seems the pod gets never scheduled
    pod_spec = None
    if affinity is None:
        pod_spec = client.V1PodSpec(containers=[container])
    else:
        pod_spec = client.V1PodSpec(containers=[container], affinity=affinity)

    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels=labels), spec=pod_spec
    )

    # spec
    spec = client.V1DeploymentSpec(
        replicas=replicas, selector=selector, template=template
    )
    deployment = client.V1Deployment(
        api_version="apps/v1", kind="Deployment", metadata=metadata, spec=spec
    )
    return deployment


def check_applications(_applications, name, namespace, logger):

    label_selector = f"app={name}"
    if wait_for_pods_ready(core_v1, namespace, label_selector):
        # Retrieve pods for this deployment (simplified: only first pod)
        pods = core_v1.list_namespaced_pod(
            namespace=namespace, label_selector=f"app={name}"
        )
        if not pods.items:
            logger.info("No pods found yet, will requeue")
            return {"requeue": True}

        # sort applications by key 'order'
        #  if order is missing, the application is set to the end
        applications = sorted_list = sorted(
            _applications, key=lambda d: d.get("order", float("inf"))
        )

        for pod in pods.items:
            container_name = pod.spec.containers[0].name

            for app in applications:
                zip_url = app.get("appUrl")
                app_name = app.get("name")
                zip_name = zip_url.split("/")[-1]

                # check, if app is present
                app_info_cmd = [
                    "/bin/sh",
                    "-c",
                    f"/opt/xyna/xyna_001/server/xynafactory.sh listapplications | grep {app_name}",
                ]
                logger.info(
                    f"Getting app-info for {app_name} in pod {pod.metadata.name}"
                )
                output = exec_command_in_pod(
                    namespace, pod.metadata.name, container_name, app_info_cmd, logger
                )
                logger.info(f"App info output: {output}")
                version_str = fetch_second_quote_content(output)

                if version_str is None:

                    # Download the zip inside the pod and run import CLI command
                    download_cmd = ["curl", "-o", f"/tmp/{zip_name}", zip_url]
                    logger.info(
                        f"Downloading {zip_url} (application '{app_name}') inside pod {pod.metadata.name}"
                    )
                    output = exec_command_in_pod(
                        namespace,
                        pod.metadata.name,
                        container_name,
                        download_cmd,
                        logger,
                    )
                    logger.info(f"Download output: {output}")

                    import_cmd = [
                        "/opt/xyna/xyna_001/server/xynafactory.sh",
                        "importapplication",
                        "-filename",
                        f"/tmp/{zip_name}",
                    ]
                    logger.info(f"Importing file {zip_name} in pod {pod.metadata.name}")
                    output = exec_command_in_pod(
                        namespace, pod.metadata.name, container_name, import_cmd, logger
                    )
                    logger.info(f"Import output: {output}")

                    # get version
                    app_info_cmd = [
                        "/bin/sh",
                        "-c",
                        f"/opt/xyna/xyna_001/server/xynafactory.sh listapplications | grep {app_name}",
                    ]
                    logger.info(
                        f"Getting app-info for {app_name} in pod {pod.metadata.name}"
                    )
                    output = exec_command_in_pod(
                        namespace,
                        pod.metadata.name,
                        container_name,
                        app_info_cmd,
                        logger,
                    )
                    logger.info(f"App info output: {output}")
                    version_str = fetch_second_quote_content(output)

                start_cmd = [
                    "/opt/xyna/xyna_001/server/xynafactory.sh",
                    "startapplication",
                    "-applicationName",
                    f'"{app_name}"',
                    "-versionName",
                    f'"{version_str}"',
                ]
                logger.info(f"Starting app {app_name} in pod {pod.metadata.name}")
                output = exec_command_in_pod(
                    namespace, pod.metadata.name, container_name, start_cmd, logger
                )
                logger.info(f"Start output: {output}")

    else:
        # Timeout or pod not ready, handle accordingly
        logger.error(
            f"Failed to finish deployment {name}, pod didn't get ready: {str(e)}"
        )


@kopf.on.create("xyna.com", "v1alpha1", "xynafactoryservices")
def on_create(spec, name, namespace, logger, **kwargs):

    logger.debug(f"creating deployment '{name}' in namespace {namespace}")

    image = spec.get("image", "xynafactory/xynafactory:latest")
    replicas = spec.get("replicas", 1)
    applications = spec.get("applications", [])
    servicePorts = spec.get("servicePorts", [])
    nodeLabels = spec.get("nodeLabels", None)

    logger.debug(f"collecting {len(servicePorts)} service ports")
    services = [
        get_service_manifest(servicePort, name, namespace, logger)
        for servicePort in servicePorts
    ]
    logger.debug(f"Applying deployments for services")

    tcpProbePort = get_tcp_port_for_probe(servicePorts)
    for service in services:

        core_v1.create_namespaced_service(namespace=namespace, body=service["body"])
        logger.info(
            f"Created service {service['serviceName']} in namespace {namespace}"
        )

    logger.debug(f"Preparing deployment manifest {name}")

    deployment_manifest = make_deployment_object(
        name, namespace, replicas, image, nodeLabels, tcpProbePort
    )
    kopf.adopt(deployment_manifest)  # Mark ownership

    try:
        apps_v1.create_namespaced_deployment(
            namespace=namespace, body=deployment_manifest
        )
        logger.info(f"Created Deployment {name}-deployment")
    except ApiException as e:
        if e.status == 409:
            apps_v1.patch_namespaced_deployment(
                name + "-deployment", namespace, deployment_manifest
            )
            logger.info(f"Patched existing Deployment {name}-deployment")
        else:
            raise

    # Optionally handle exec inside pod to import each application zip here
    # This requires listing pods with label app=name and running kubectl exec equivalents

    check_applications(applications, name, namespace, logger)


@kopf.on.update("xyna.com", "v1alpha1", "xynafactoryservices")
def on_update(spec, name, namespace, logger, **kwargs):
    desired_replicas = spec.get("replicas", 1)
    patch = {"spec": {"replicas": desired_replicas}}
    try:
        apps_v1.patch_namespaced_deployment(name + "-deployment", namespace, patch)
        applications = spec.get("applications", [])
        check_applications(applications, name, namespace, logger)

        logger.info(
            f"Scaled deployment {name}-deployment to {desired_replicas} replicas"
        )

    except ApiException as e:
        logger.error(f"Failed to patch deployment replicas: {e}")


@kopf.on.delete("xyna.com", "v1alpha1", "xynafactoryservices")
def on_delete(spec, name, namespace, logger, **kwargs):
    deployment_name = f"{name}-deployment"
    try:
        apps_v1.delete_namespaced_deployment(deployment_name, namespace)
        logger.info(f"Deleted deployment {deployment_name} in {namespace}")
    except ApiException as e:
        logger.error(f"Failed to delete deployment {deployment_name}: {str(e)}")

    servicePorts = spec.get("servicePorts", [])
    for service in servicePorts:
        service_name = service.get("serviceName")
        if service_name:
            try:
                core_v1.delete_namespaced_service(service_name, namespace)
                logger.info(f"Deleted service {service_name} in {namespace}")
            except ApiException as e:
                logger.error(f"Failed to delete service {service_name}: {str(e)}")
