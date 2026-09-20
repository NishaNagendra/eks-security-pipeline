import base64
import json
import boto3
import botocore.session
from botocore.signers import RequestSigner
from kubernetes import client
from kubernetes.client.rest import ApiException

STS_TOKEN_EXPIRES_IN = 60
FINDING_TYPE = "PrivilegeEscalation:Kubernetes/AnomalousBehavior.RoleBindingCreated"


def get_bearer_token(cluster_name, region):
    session = botocore.session.get_session()
    client_sts = session.create_client('sts', region_name=region)
    service_id = client_sts.meta.service_model.service_id

    signer = RequestSigner(
        service_id,
        region,
        'sts',
        'v4',
        session.get_credentials(),
        session.get_component('event_emitter')
    )

    params = {
        'method': 'GET',
        'url': f'https://sts.{region}.amazonaws.com/?Action=GetCallerIdentity&Version=2011-06-15',
        'body': {},
        'headers': {'x-k8s-aws-id': cluster_name},
        'context': {}
    }

    signed_url = signer.generate_presigned_url(
        params,
        region_name=region,
        expires_in=STS_TOKEN_EXPIRES_IN,
        operation_name=''
    )

    base64_url = base64.urlsafe_b64encode(signed_url.encode('utf-8')).decode('utf-8')
    return 'k8s-aws-v1.' + base64_url.rstrip('=')


def lambda_handler(event, context):
    finding_type = event['detail']['type']
    print(f"Received finding: {finding_type}")

    if finding_type != FINDING_TYPE:
        print("Not the finding type we handle, ignoring")
        return {"statusCode": 200, "body": "Ignored - not our finding type"}

    region = event['region']
    cluster_name = event['detail']['resource']['eksClusterDetails']['name']
    print(f"Target cluster: {cluster_name}")

    eks = boto3.client('eks', region_name=region)
    cluster = eks.describe_cluster(name=cluster_name)['cluster']
    endpoint = cluster['endpoint']
    ca_data = cluster['certificateAuthority']['data']

    with open('/tmp/ca.crt', 'w') as f:
        f.write(base64.b64decode(ca_data).decode('utf-8'))

    token = get_bearer_token(cluster_name, region)

    configuration = client.Configuration()
    configuration.host = endpoint
    configuration.ssl_ca_cert = '/tmp/ca.crt'
    configuration.api_key = {"authorization": f"Bearer {token}"}

    api_client = client.ApiClient(configuration)
    rbac_api = client.RbacAuthorizationV1Api(api_client)

    binding_name = None
    try:
        k8s_details = event['detail']['resource'].get('kubernetesDetails', {})
        binding_name = k8s_details.get('kubernetesUserDetails', {}).get('username')
    except (KeyError, TypeError):
        pass

    if not binding_name:
        print("Could not extract binding name from finding, listing all ClusterRoleBindings to find suspicious ones")
        bindings = rbac_api.list_cluster_role_binding()
        for b in bindings.items:
            if b.role_ref.name == "cluster-admin" and "exploit" in b.metadata.name.lower():
                binding_name = b.metadata.name
                break

    if not binding_name:
        print("No matching ClusterRoleBinding found to remediate")
        return {"statusCode": 200, "body": "No action taken - could not identify binding"}

    try:
        rbac_api.delete_cluster_role_binding(name=binding_name)
        print(f"Deleted malicious ClusterRoleBinding: {binding_name}")
        return {"statusCode": 200, "body": f"Remediated: deleted {binding_name}"}
    except ApiException as e:
        print(f"Failed to delete binding: {e}")
        return {"statusCode": 500, "body": str(e)}
