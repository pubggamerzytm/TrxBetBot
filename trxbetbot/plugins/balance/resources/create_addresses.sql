CREATE TABLE addresses (
    address TEXT NOT NULL PRIMARY KEY,
    privkey TEXT NOT NULL,
	date_time DATETIME DEFAULT CURRENT_TIMESTAMP
)