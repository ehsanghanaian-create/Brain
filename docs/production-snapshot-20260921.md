# Production source snapshot — 2026-09-21

This revision imports the source archive used for the running production release
`20260920-phonetab-v1` (backend and frontend).

- Source: `/opt/seo-brain/builds/phonetab-20260920.tar.gz` on the production host.
- All 176 installed backend package files matched the archive byte for byte.
- The frontend build log confirms successful creation of the running image tag.
- Both running application containers were healthy during verification.
- Runtime databases, site data, credentials, logs and production environment files
  are intentionally excluded. This repository is a source backup, not a data backup.
- The existing local development checkout was not used as the deployment source.

The production build uses `deploy/seo-brain/backend.online.Dockerfile` from the
repository root and `deploy/seo-brain/frontend.online.Dockerfile` with `frontend/`
as its build context. Production environment and runtime volumes must be supplied
separately; the checked-in Compose examples are not a copy of live secrets/config.
