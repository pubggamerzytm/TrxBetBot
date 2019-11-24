CREATE TABLE tips (
    from_user_id TEXT NOT NULL,
    to_user_id TEXT NOT NULL,
    amount INTEGER NOT NULL,
	date_time DATETIME DEFAULT CURRENT_TIMESTAMP,
	FOREIGN KEY(from_user_id) REFERENCES users(user_id),
    FOREIGN KEY(to_user_id) REFERENCES users(user_id)
)