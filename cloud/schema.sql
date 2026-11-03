-- Each revision is an immutable complete snapshot. One conditional INSERT is
-- the publication transaction, so readers never see a partially uploaded list.
CREATE TABLE IF NOT EXISTS revisions (
  version INTEGER PRIMARY KEY,
  records TEXT NOT NULL CHECK(json_valid(records)),
  published_utc TEXT NOT NULL,
  published_by TEXT NOT NULL
);
INSERT OR IGNORE INTO revisions VALUES (0, '[]', '1970-01-01T00:00:00Z', 'bootstrap');
