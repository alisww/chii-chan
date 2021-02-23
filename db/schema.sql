CREATE TABLE tws (
  manga INTEGER,
  user INTEGER,
  warning TEXT
);

CREATE TABLE ratings (
  manga INTEGER,
  user INTEGER,
  rating REAL
);

CREATE TABLE notifications (
  manga INTEGER,
  user INTEGER,
  guild INTEGER
);

CREATE TABLE latest_release (
  manga INTEGER UNIQUE,
  latest TEXT
);

CREATE TABLE guilds (
  guild INTEGER UNIQUE,
  notify BOOLEAN,
  notify_channel INTEGER
);

CREATE TABLE lists (
  list TEXT,
  user INTEGER,
  items BLOB
);

-- TWs:
-- (INTEGER 'manga', INTEGER 'user', TEXT 'warning')
-- ratings
-- (INTEGER 'manga', INTEGER 'user', REAL 'rating')
-- notifications
-- (INTEGER 'manga', INTEGER 'user', INTEGER 'guild')
-- latest release
-- (UNIQUE INTEGER 'manga', TEXT 'latest')
-- guild settings
-- (UNIQUE INTEGER 'guild', BOOL 'notify', INTEGER 'notify_channel')
-- lists
-- (TEXT 'list', INTEGER 'user', BLOB 'items') # items is json encoded
