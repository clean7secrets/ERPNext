# Books by Ronak Patel & Associates — server notes

ERPNext v16 (frappe_docker, compose project `erpnext`) on the BigRock VPS, site `books.caronakpatel.com`,
bound to 127.0.0.1:8085 behind nginx + Let's Encrypt.

- `apps/rpa_integration` — the custom app: per-client feature gating, provisioning API and single sign-on for
  the portal, per-client numbering, the 7 invoice layouts, white-label branding, the My Business client home.
- `deploy/Dockerfile.rpa` — builds `rpa-erpnext:v16` from `rpa-erpnext-base:v16` with this app and Devanagari fonts.

Deploy on the server:
1. Copy `apps/rpa_integration` to `/opt/erpnext/rpa_integration`.
2. `cd /opt/erpnext && docker build -t rpa-erpnext:v16 -f Dockerfile.rpa .`
3. `docker compose -p erpnext -f /opt/erpnext/erpnext.yaml up -d`
4. `docker compose -p erpnext -f /opt/erpnext/erpnext.yaml exec backend bench --site books.caronakpatel.com migrate`

Secrets (DB/admin passwords, API keys, SSO secret) live only in `/root/erpnext-secrets.env` on the server — never in this repo.
