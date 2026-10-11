# WordPress REST origin pin for a split storefront

SEO Brain may use `api.salimore.com` as the WordPress URL while that hostname's
public virtual host does not serve the WordPress installation. For the
read-only REST connector, the backend can pin one configured WordPress host to
the official origin IP without changing DNS, storefront crawling, or Nginx.

Set all three variables on the **backend only**:

```text
WP_REST_PINNED_HOST=api.salimore.com
WP_REST_ORIGIN_HOST=salimore.com
WP_REST_ORIGIN_IP=<verified WordPress origin IP>
```

The connector requests the existing site `wp_url`, but opens the TCP connection
to the pinned IP. HTTP `Host`, TLS SNI, and certificate verification use
`WP_REST_ORIGIN_HOST`. Other site hosts and the public crawler use normal DNS.
An incomplete set of variables fails closed. Unset all three to restore the
original routing. This does not repair the public `api.salimore.com` host or
checkout; those need a separate hosting/DNS change and verification.

Before enabling the pin, test REST root, types, taxonomies, categories, posts,
and the site health route from the backend host with the origin's host/SNI and
verify 2xx JSON responses. Back up the live Compose file and SQLite databases
before changing production configuration. After enabling it, test the
WordPress connection, run a `stage=full` sync, and verify its status and
content counts. `graph_only` success does not verify WordPress sync.
