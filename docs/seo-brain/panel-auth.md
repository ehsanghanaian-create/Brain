# Panel accounts and activity log

The dashboard now uses named accounts. Provision the first administrator **locally** after running the current migrations (0027 and 0028):

```powershell
& .\.venv\Scripts\python.exe backend/cli/bootstrap_panel_admin.py
```

The script creates `admin` with a random password and writes the initial credentials to the ignored `data/panel-initial-admin.txt`. It refuses to replace an existing administrator. Change the password on the Users page after first login, then remove the initial credentials file using the normal local file workflow. Existing directory entries without credentials remain inactive for login until an admin assigns them a username and password.

Configure the internal service token in the backend `.env` (`API_TOKEN`) and the same value in `frontend/.env.local` (`SEO_BRAIN_API_TOKEN`). This token is for server components and automation. The browser uses an opaque 12-hour HttpOnly session cookie; the Next proxy forwards the session bearer token to FastAPI and never forwards the service token for browser API requests. Only the administrator should be able to read the service token files. Set `SEO_BRAIN_API_URL` to the loopback FastAPI address.

Roles:

| Role | Dashboard | API |
| --- | --- | --- |
| admin | All pages | Full access, including user management and audit |
| analyst | Overview, work command center, reports, sites, graph, traffic, opportunities, ads data | Read-only analytical and work endpoints |
| call_center | Call-center page | Call ledger and safe operator/site/traffic lookups |

Backend role checks are applied to bearer sessions. Direct URL entry or a hand-crafted browser API request does not bypass them. Trusted service-token requests remain available for automation and must not be exposed to users. Disabling a user or changing their role/password invalidates existing sessions. The last active admin cannot be disabled or demoted.

Successful panel mutations are recorded in `panel_audit_log` with actor, time, HTTP action, endpoint, status, request ID, and changed field names. Login and logout are logged. Password values, tokens, and call contents are never written to the audit table. Admins can review the newest entries on Users or via `GET /api/v1/auth/audit`.

Five failed login attempts for one username pause further attempts for 15 minutes. The failure counter resets after a successful login.

Deployment sequence: back up the database, apply migrations, configure both service-token environment variables, provision the first admin on the target host, then restart API and Next. Do not copy the local initial credentials to production. Verify login and one account for each role before exposing the panel.
