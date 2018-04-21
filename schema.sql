DROP TABLE IF EXISTS queued_entries;
CREATE TABLE queued_entries (
path CHAR(100) UNIQUE,
client_modified DATETIME,
time_taken DATETIME,
height MEDIUMINT UNSIGNED,
width MEDIUMINT UNSIGNED,
latitude DECIMAL(9,6),
longitude DECIMAL(9,6)
);
