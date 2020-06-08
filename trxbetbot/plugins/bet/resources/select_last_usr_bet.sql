SELECT max(date_time), delay
FROM bets
WHERE usr_id = ?