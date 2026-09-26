# anatomy-chatbot-eks

Cloud-revamped anatomy tutoring chatbot targeting **Amazon EKS**.

Monorepo derived from [`maleonpitt/anatomy-chatbot`](https://github.com/maleonpitt/anatomy-chatbot).  
**No EC2 / CodeDeploy path** — API deploys via container image → ECR → EKS.

```text
GitHub Actions (CI)     → test / build → (later) push API image to Amazon ECR

Frontend:
Browser → CloudFront → private S3 → React SPA   (frontend/)

Backend:
Browser → ALB Ingress → EKS Service → Pods      (backend/)
  → image from ECR
  → FastAPI + Uvicorn
  → DynamoDB, Pinecone, OpenAI
```

## Repo layout

| Path | Purpose |
|------|---------|
| `frontend/` | React SPA (Create React App) |
| `backend/` | FastAPI RAG API + Docker (Uvicorn) |
| `k8s/` | EKS manifests (Deployment, Service, Ingress, ConfigMap, …) |
| `terraform/` | ECR / EKS (opt-in) / S3+CloudFront — validate only until authorized |

## Status

- [x] Phase 1 — public repo scaffold  
- [x] Phase 2 — app code in monorepo, secrets stripped, no CodeDeploy/EC2 legacy  
- [x] Phase 3 — FastAPI + Uvicorn production image (non-root)  
- [x] Phase 4 — Kubernetes manifests (industry-style ConfigMap + External Secrets example)  
- [x] Phase 5 — Terraform sketch (ECR, optional EKS, S3/CloudFront; no live apply by default)  
- [x] Phase 6 — GitHub Actions (CI + image build; ECR/S3 push gated on manual dispatch)  

## CI / CD

See [`.github/workflows/README.md`](.github/workflows/README.md).

- **CI** on every PR: backend healthz smoke, frontend build, API `docker build`, `terraform validate`
- **API image**: builds on backend changes; ECR push is **manual** (`push_to_ecr`)
- **Frontend static**: manual only; S3 sync gated behind `push_frontend`

## Local run (dev)

```bash
# API
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys locally — do not commit
uvicorn app:app --host 0.0.0.0 --port 5000 --reload

# UI (other terminal)
cd frontend
npm ci
npm start
```

Health check: `GET http://localhost:5000/healthz`  
API docs (dev): `http://localhost:5000/docs`

## Docker (API)

```bash
cd backend
docker build -t anatomy-chatbot-api:local .
docker run --rm -p 5000:5000 --env-file .env anatomy-chatbot-api:local
```

## Safety

- Never commit `.env` or real API keys.
- Do not run `terraform apply` against a real account unless explicitly authorized.
- Prefer Secrets Manager / IRSA for cluster workloads later.

## License / ownership

University of Pittsburgh — HEILab related work. Confirm redistribution terms for public use of course materials under `backend/transcripts/`.
