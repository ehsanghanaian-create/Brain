-- Project-defined task fields with typed values.
CREATE TABLE IF NOT EXISTS work_custom_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id TEXT NOT NULL REFERENCES sites(site_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    field_type TEXT NOT NULL CHECK (field_type IN ('text','number','date','select')),
    options_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    UNIQUE(site_id,name)
);
CREATE INDEX IF NOT EXISTS idx_work_custom_fields_site ON work_custom_fields(site_id,id);

CREATE TABLE IF NOT EXISTS work_custom_values (
    field_id INTEGER NOT NULL REFERENCES work_custom_fields(id) ON DELETE CASCADE,
    work_item_id INTEGER NOT NULL REFERENCES work_items(id) ON DELETE CASCADE,
    site_id TEXT NOT NULL REFERENCES sites(site_id) ON DELETE CASCADE,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(field_id,work_item_id)
);
CREATE INDEX IF NOT EXISTS idx_work_custom_values_item ON work_custom_values(site_id,work_item_id,field_id);
