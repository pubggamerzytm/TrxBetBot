CREATE TABLE bets (
    bet_address TEXT NOT NULL PRIMARY KEY,
    bet_chars TEXT NOT NULL,
	usr_id TEXT NOT NULL,
	usr_address TEXT,
    usr_amount INTEGER,
    bet_trx_id TEXT,
    bet_trx_block INTEGER,
    bet_trx_block_hash TEXT,
    bet_won TEXT,
    pay_amount INTEGER,
    pay_trx_id TEXT,
	date_time DATETIME DEFAULT CURRENT_TIMESTAMP,
	rtn_trx_id TEXT,
	delay INTEGER,
	FOREIGN KEY(bet_address) REFERENCES addresses(address)
)