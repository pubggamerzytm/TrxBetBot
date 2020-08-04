SELECT DISTINCT	usr_address
FROM (SELECT * FROM bets WHERE usr_address IS NOT NULL)
WHERE date_time >= datetime('now', ?)