CREATE TABLE users (
	user_id TEXT NOT NULL PRIMARY KEY,
	username TEXT NOT NULL,
	first_name TEXT NOT NULL,
	last_name TEXT,
	language TEXT,
	address TEXT NOT NULL,
	date_time DATETIME DEFAULT CURRENT_TIMESTAMP,
	FOREIGN KEY(address) REFERENCES addresses(address)
)