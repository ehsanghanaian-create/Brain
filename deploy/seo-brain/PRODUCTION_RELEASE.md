# Production source preflight

The running containers are the production baseline. The checkout at
`/opt/seo-brain/builds/deploy-20261006-work-platform` has previously lagged
behind live images. On 2026-10-15, building its older frontend source removed
Ads Data features that had been deployed on 2026-10-14.

Before every release:

1. Record the current frontend and backend image tags from
   `/opt/seo-brain/compose.production.yaml` and keep those images for rollback.
2. Compare the candidate frontend source with the source snapshot used for the
   **current** frontend image. Compare backend files with the installed
   `seo_brain` package in the running backend container. Resolve every
   difference before building. A healthy container does not prove that the
   checkout is current.
3. Build in a separate directory, check the new images independently, then
   change one Compose service at a time. Verify both container health and the
   public panel route; restore the recorded tags if either check fails.
4. After a successful release, sync the release source back to the server
   checkout and retain a copy of the prior source and Compose file.

The 2026-10-15 recovery used the 2026-10-14 frontend source snapshot at
`/opt/seo-brain/builds/ads-ip-exclusion-20261014-frontend` and the package
from the live backend image. Its staged source is at
`/opt/seo-brain/builds/ads-recovery-20261015`.
