SELECT Count(*)
FROM addresses
WHERE date_time >= datetime('now', ?)