--cache (INTEGER 'manga', BLOB data) # data is json encoded!
-- name_cache (TEXT 'manga', INTEGER 'id')
CREATE TABLE cache (
  manga INTEGER,
  data BLOB
);

CREATE TABLE name_cache (
  manga TEXT,
  id INTEGER
);
