# EKS Security Pipeline

An end-to-end AWS EKS security architecture built with Terraform, demonstrating network isolation, least-privilege IAM/RBAC, container image scanning, and automated threat detection & remediation.

## Architecture

1. **Infrastructure as Code (Terraform)** - VPC with public/private subnets across 2 AZs, NAT Gateway, Internet Gateway, EKS cluster (v1.31) with a managed node group.
2. **Private-subnet worker nodes** - EKS worker nodes run exclusively in private subnets with no public IPs; verified via `kubectl get nodes -o wide` showing `EXTERNAL-IP <none>`.
3. **IAM Roles for Service Accounts (IRSA)** - A Kubernetes service account assumes a scoped IAM role via the cluster's OIDC provider, granted `s3:GetObject`/`s3:ListBucket` on exactly one S3 bucket. Verified: the pod can access its scoped bucket but receives `AccessDenied` on account-wide `s3 ls`.
4. **Kafka with Pod Security Standards + NetworkPolicies** - A KRaft-mode Kafka broker (`apache/kafka:3.8.0`) running under `pod-security.kubernetes.io/enforce: restricted` (non-root, no privilege escalation, all capabilities dropped, seccomp required), plus default-deny NetworkPolicies with explicit allow rules for intra-Kafka traffic and DNS.
5. **Trivy CI gate** - A GitHub Actions workflow (`.github/workflows/trivy-scan.yml`) builds a Docker image and fails the pipeline (`exit-code: 1`) on any Critical/High CVE, using `aquasecurity/trivy-action`.
6. **RBAC privilege-escalation simulation** - A deliberately misconfigured ClusterRole granting `create` on ClusterRoleBindings + `bind` on `cluster-admin` - a realistic "scoped down, but scoped to the wrong thing" misconfiguration. A pod using this identity escalates itself to `cluster-admin` by creating its own ClusterRoleBinding.
7. **GuardDuty + EventBridge + Lambda auto-remediation** - GuardDuty EKS Protection (Kubernetes audit log monitoring) watches for finding type `PrivilegeEscalation:Kubernetes/AnomalousBehavior.RoleBindingCreated`. An EventBridge rule routes matching findings to a VPC-attached Lambda function, which authenticates to the private EKS API server (via a SigV4-signed STS token, replicating the `aws-iam-authenticator` mechanism) and deletes the malicious ClusterRoleBinding using least-privilege Kubernetes RBAC (`get`/`list`/`delete` on ClusterRoleBindings only - no ability to create new bindings or escalate itself).

## What's real vs. simulated

Everything above is live, deployed AWS/Kubernetes infrastructure - not mocked. Two things are worth being upfront about:

- **GuardDuty's real-world detection isn't instant.** ML-based EKS findings can take from minutes to hours to surface organically after the triggering event. Rather than wait indefinitely, the Lambda was tested directly via `aws lambda invoke` against a realistic finding payload matching GuardDuty's documented schema for this finding type - proving the authentication, authorization, and remediation logic work correctly end-to-end. The EventBridge rule connecting real GuardDuty findings to this Lambda is fully deployed and would fire automatically on an organic detection.
- **The finding payload's exact field structure** (`detail.resource.kubernetesDetails.kubernetesUserDetails.username`) was inferred from GuardDuty's general finding schema patterns rather than a captured live finding for this specific type. The Lambda includes a fallback that searches for any `cluster-admin` ClusterRoleBinding with "exploit" in its name if the expected field path doesn't match - a safety net for schema variations.

## Repository structure

- `main.tf`, `vpc.tf`, `networking.tf` - provider config, VPC, subnets, routing
- `eks.tf` - EKS cluster, node group, access entries
- `iam.tf` - IAM roles for cluster, nodes, IRSA demo, Lambda
- `s3.tf` - IRSA demo bucket
- `guardduty.tf` - GuardDuty detector with EKS Protection
- `lambda.tf`, `lambda_remediation.py` - remediation Lambda and its Terraform resource
- `eventbridge.tf` - EventBridge rule routing GuardDuty findings to Lambda
- `*.yaml` - Kubernetes manifests (IRSA service account, Kafka, RBAC privesc demo, Lambda's Kubernetes RBAC)
- `Dockerfile`, `app.py` - minimal demo app for the Trivy CI gate
- `.github/workflows/trivy-scan.yml` - CI vulnerability scanning

## Running this yourself

Requires: AWS CLI, Terraform, kubectl, an AWS account.

```bash
terraform init
terraform apply
aws eks update-kubeconfig --region us-east-1 --name security-pipeline-cluster
kubectl apply -f irsa-demo-sa.yaml -f irsa-test-pod.yaml
kubectl apply -f kafka-namespace.yaml -f kafka-network-policy.yaml -f kafka-statefulset.yaml
kubectl apply -f rbac-privesc-demo.yaml
kubectl apply -f lambda-remediation-rbac.yaml
```

**Note on cost**: this provisions an EKS cluster, NAT Gateway, and EC2 instances that incur hourly charges (~$0.23/hr combined). Run `terraform destroy` when done.
