CREATE TABLE users (
	user_id TEXT NOT NULL PRIMARY KEY,
	username TEXT NOT NULL,
	first_name TEXT NOT NULL,
	last_name TEXT,
	language TEXT,
	date_time DATETIME DEFAULT CURRENT_TIMESTAMP
)