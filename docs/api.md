# API reference

The platform is API-first (`src/webapi/`); the UI consumes only this API. The API serves
interactive OpenAPI docs at `/docs` (internal in the full stack; on the local fake-engine dev
server it's `http://localhost:8080/docs`). Selected endpoints:

**Auth / users / credentials / admin**
- `GET /health`, `GET /version`
- `POST /auth/jwt/login` (form: `username`, `password`) → `{access_token}`; `POST /auth/jwt/logout`
- `POST /auth/forgot-password`, `POST /auth/reset-password`, `POST /auth/accept-invite`
- `GET /users/me`, `POST /users/me/change-password`
- Admin: `POST /users`, `GET /users`, `PATCH /users/{id}`, `DELETE /users/{id}`, `POST /users/{id}/reset-password`
- Credentials (owner-private, secrets never returned): `POST`/`GET`/`DELETE /credentials`
- Admin config: `GET /admin/config`, `PUT /admin/config`
- Invitations: `POST`/`GET /invitations`, `DELETE /invitations/{id}`

**Repositories / jobs / runs**
- Repositories: `POST`/`GET /repositories`, `GET`/`PATCH`/`DELETE /repositories/{id}`,
  `POST /repositories/{id}/upload`, `POST /repositories/{id}/webhook`,
  `GET`/`POST`/`DELETE /repositories/{id}/access`
- Jobs: `POST`/`GET /jobs`, `GET`/`PATCH`/`DELETE /jobs/{id}`, `POST /jobs/{id}/run`
- Runs: `GET /runs`, `GET`/`DELETE /runs/{id}`, `POST /runs/{id}/cancel`
- Logs: `GET /runs/{id}/logs?offset=` (paged), `GET /runs/{id}/logs/stream` (SSE)
- Reports & artifacts: `GET /runs/{id}/report`, `GET /runs/{id}/artifacts[/{kind}]`, on-demand report export `GET /runs/{id}/report/export/{docx|pdf}`

**Scheduling & webhooks**
- Schedules: `POST`/`GET /schedules`, `PATCH`/`DELETE /schedules/{id}` (`once` / `recurring` / `gitlab_mr`)
- `POST /webhooks/gitlab` (unauthenticated, `X-Gitlab-Token` verified) — MR events trigger matching schedules.

**Dashboards & metrics**
- `GET /dashboard/metrics`, `GET /runs/{id}/metrics`, `GET /repositories/{id}/metrics/timeline`
