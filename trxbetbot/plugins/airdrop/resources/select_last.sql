SELECT * FROM (
SELECT * FROM bets
WHERE usr_amount >= ?
ORDER BY rowid DESC LIMIT ?)
ORDER BY rowid ASC;