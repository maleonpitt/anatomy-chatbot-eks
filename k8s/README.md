# Kubernetes manifests for the anatomy chatbot API on Amazon EKS

Apply-ready **design** only. Do **not** apply to a live cluster until ECR image, IAM/IRSA, secrets, and ACM are real.

## Objects

| File | Purpose |
|------|---------|
| `namespace.yaml` | Isolate resources in `anatomy-chatbot` |
| `configmap.yaml` | Non-secret config (region, CORS, table names) |
| `secret.example.yaml` | Documents required secret keys — placeholders only |
| `external-secret.example.yaml` | Industry pattern: sync from AWS Secrets Manager |
| `deployment.yaml` | Pods running FastAPI/Uvicorn image + ServiceAccount |
| `service.yaml` | ClusterIP fronting Pods |
| `ingress.yaml` | ALB via AWS Load Balancer Controller |
| `hpa.yaml` | Optional CPU-based autoscaling |

## Suggested apply order (when authorized)

```bash
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
# Prefer External Secrets over applying secret.example.yaml with real values
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml
kubectl apply -f hpa.yaml
```

## Traffic path

```text
Browser → ALB (Ingress) → Service:80 → Pod:5000 (Uvicorn) → DynamoDB / Pinecone / OpenAI
```

Frontend stays on **S3 + CloudFront** (not in this folder).

## Before a real deploy

1. Build/push image to ECR; set `image:` in `deployment.yaml`
2. Create Secrets Manager secret JSON; enable External Secrets (or inject Secret out-of-band)
3. Annotate ServiceAccount with IRSA role for DynamoDB (and Secrets Manager if used)
4. Set ConfigMap `CORS_ORIGINS` / `PINECONE_INDEX_NAME`
5. Set Ingress ACM certificate annotation
6. Confirm AWS Load Balancer Controller is installed on the cluster
