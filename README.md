# anatomy-chatbot-eks

Cloud-revamped anatomy tutoring chatbot for **Amazon EKS**.

This repo starts from the University of Pittsburgh HEILab anatomy chatbot and evolves it into an apply-ready, production-oriented layout:

```text
GitHub Actions (CI)
  → test / build
  → (future) push API image to Amazon ECR

Frontend:
Browser → CloudFront → private S3 → static React SPA

Backend:
Browser → ALB Ingress → EKS Service → Pods
  → container image from ECR
  → Flask API + Gunicorn (planned)
  → DynamoDB, Pinecone, OpenAI
```

## Status

**Phase 1:** repository scaffold only.

Application code, Kubernetes manifests, hardened Docker image, and Terraform for ECR/EKS will land in later phases.

## Safety

- No live `terraform apply` required to use this repo as a learning / design artifact.
- Do not commit secrets (`.env`, API keys, PEM files, tokens).
- Prefer placeholder env vars and example configs.

## Source lineage

Derived from [`maleonpitt/anatomy-chatbot`](https://github.com/maleonpitt/anatomy-chatbot).

## License / ownership

University of Pittsburgh — HEILab related work. Confirm redistribution terms before treating this as fully public product code.
