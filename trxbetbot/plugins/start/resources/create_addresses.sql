CREATE TABLE addresses (
    user_id TEXT NOT NULL PRIMARY KEY,
    address TEXT NOT NULL,
    privkey TEXT NOT NULL,
	date_time DATETIME DEFAULT CURRENT_TIMESTAMP,
	FOREIGN KEY(user_id) REFERENCES users(user_id)
)