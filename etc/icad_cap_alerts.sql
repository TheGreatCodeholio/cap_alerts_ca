  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL
);

-- Creating the Alerts Table
CREATE TABLE IF NOT EXISTS ca_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace TEXT,
    identifier TEXT,
    sender TEXT,
    sent BIGINT,
    status TEXT,
    msgType TEXT,
    source TEXT,
    scope TEXT,
    note TEXT,
    map_file TEXT,
    is_active INT,
    parent_alert_id INT,
    FOREIGN KEY (parent_alert_id) REFERENCES ca_alerts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ca_alert_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id INTEGER,
    language TEXT,
    category TEXT,
    event TEXT,
    responseType TEXT,
    urgency TEXT,
    severity TEXT,
    certainty TEXT,
    audience TEXT,
    effective BIGINT,
    expires BIGINT,
    sender_name TEXT,
    headline TEXT,
    description TEXT,
    instruction TEXT,
    web TEXT,
    audio_url TEXT,
    image_url TEXT,
    FOREIGN KEY (alert_id) REFERENCES ca_alerts(id) ON DELETE CASCADE
);

-- Creating the Areas Table
CREATE TABLE IF NOT EXISTS ca_alert_areas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    info_id INTEGER,
    alert_id INTEGER,
    areaDesc TEXT,
    polygon TEXT,
    FOREIGN KEY (alert_id) REFERENCES ca_alerts(id) ON DELETE CASCADE,
    FOREIGN KEY (info_id) REFERENCES ca_alert_info(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ca_alert_geocodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id INTEGER,
    area_id INTEGER,
    geocode_key TEXT,
    geocode_value TEXT,
    FOREIGN KEY (area_id) REFERENCES ca_alert_areas(id) ON DELETE CASCADE,
    FOREIGN KEY (alert_id) REFERENCES ca_alerts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ca_alert_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_alert_id INTEGER,
    identifier_reference TEXT,
    FOREIGN KEY (parent_alert_id) REFERENCES ca_alerts(id) ON DELETE CASCADE
);