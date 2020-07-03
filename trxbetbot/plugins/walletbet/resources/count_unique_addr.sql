SELECT DISTINCT	usr_address
FROM bets
WHERE date_time >= datetime('now', ?)