CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS weather_cache (key TEXT PRIMARY KEY, fetched REAL NOT NULL, payload TEXT);
CREATE TABLE IF NOT EXISTS contexts (token TEXT PRIMARY KEY, created REAL NOT NULL, snapshot TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS contexts_created ON contexts(created);
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY,
  received REAL NOT NULL,
  mountain TEXT NOT NULL,
  viewpoint TEXT NOT NULL,
  answer TEXT NOT NULL,
  browser_hash TEXT NOT NULL,
  context_token TEXT NOT NULL,
  snapshot TEXT NOT NULL,
  UNIQUE(context_token, browser_hash)
);
CREATE INDEX IF NOT EXISTS reports_recent ON reports(mountain, viewpoint, received);
CREATE INDEX IF NOT EXISTS reports_received ON reports(received);
CREATE INDEX IF NOT EXISTS reports_browser ON reports(mountain, viewpoint, browser_hash, received);
