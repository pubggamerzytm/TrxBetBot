CREATE TABLE automix (
	usr_id TEXT NOT NULL PRIMARY KEY,
    bet_chars TEXT NOT NULL,
    bet_amount INTEGER NOT NULL,
    updt BLOB NOT NULL,
	date_time DATETIME DEFAULT CURRENT_TIMESTAMP
)