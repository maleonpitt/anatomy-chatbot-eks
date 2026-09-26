# GitHub Actions

| Workflow | Trigger | AWS? |
|----------|---------|------|
| `ci.yml` | PR + push to `main` | No — lint/test/build/validate only |
| `api-image.yml` | push to `main` (backend paths) + manual | Build always; **ECR push only** on `workflow_dispatch` with `push_to_ecr=true` |
| `frontend-static.yml` | manual | Build always; **S3/CloudFront only** if `push_frontend=true` |

## Preferred auth for pushes

Use **OIDC** → `secrets.AWS_ROLE_TO_ASSUME` (no long-lived keys in GitHub).

Optional repository variables:

- `AWS_REGION`
- `ECR_REPOSITORY`
- `STATIC_FRONTEND_S3_BUCKET`
- `STATIC_FRONTEND_CF_DIST_ID`
- `REACT_APP_API_URL`

## Safety

Default CI and image builds **do not** create or change AWS resources.
