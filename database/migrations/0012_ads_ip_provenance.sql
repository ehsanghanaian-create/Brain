ALTER TABLE ads_click_events ADD COLUMN proxy_ip TEXT;
ALTER TABLE ads_click_events ADD COLUMN ip_confidence TEXT NOT NULL DEFAULT 'legacy_unverified';
ALTER TABLE ads_click_events ADD COLUMN ip_resolution_version TEXT NOT NULL DEFAULT '1';

UPDATE ads_click_events
SET ip_confidence='legacy_unverified', ip_resolution_version='1'
WHERE ip_confidence IS NULL OR ip_confidence='';

