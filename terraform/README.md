# Terraform — anatomy-chatbot-eks

Apply-ready **design** for:

| Flag | Resources |
|------|-----------|
| `enable_ecr` (default true) | ECR repo + scan-on-push + lifecycle |
| `enable_frontend` (default true) | Private S3 + CloudFront OAC (+ optional `/api/*` origin) |
| `enable_eks` (default **false**) | VPC + EKS managed node group + IRSA role for the API |

## Safety

- Do **not** run `terraform apply` unless you explicitly authorize a real AWS account.
- Safe local commands:

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # edit; tfvars is gitignored
terraform fmt
terraform init -backend=false
terraform validate
# terraform plan    # needs AWS credentials; still prefer not to apply
```

`enable_eks = false` by default so a mistaken apply is less likely to create a cluster/NAT bill.

## After a real EKS apply

1. Push image to `ecr_repository_url`
2. Set `k8s/deployment.yaml` image
3. Annotate ServiceAccount with `api_irsa_role_arn`
4. Install AWS Load Balancer Controller; apply `k8s/` Ingress
5. Point CloudFront `api_origin_domain` at the ALB hostname (with matching ACM cert)

## Related app manifests

See [`../k8s/README.md`](../k8s/README.md).
