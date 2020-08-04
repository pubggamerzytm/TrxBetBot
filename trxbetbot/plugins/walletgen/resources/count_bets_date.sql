SELECT Count(*)
FROM (SELECT * FROM bets WHERE usr_address IS NOT NULL)
WHERE date_time >= datetime('now', ?)