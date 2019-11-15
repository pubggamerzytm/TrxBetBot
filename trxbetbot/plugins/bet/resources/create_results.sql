CREATE TABLE results (
	bet_address TEXT NOT NULL PRIMARY KEY,
	usr_address TEXT NOT NULL,
    amount INTEGER NOT NULL,
    trx_hash TEXT NOT NULL,
    blk_hash TEXT NOT NULL,
    won INTEGER,
	date_time DATETIME DEFAULT CURRENT_TIMESTAMP
)