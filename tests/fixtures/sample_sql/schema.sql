-- Sample SQL schema for testing CodeAtlas SQL parser

CREATE TABLE users (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL,
    email   TEXT UNIQUE,
    active  INTEGER DEFAULT 1
);

CREATE TABLE orders (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    total      REAL,
    created_at TEXT
);

CREATE VIEW active_users AS
    SELECT id, name, email
    FROM users
    WHERE active = 1;

CREATE VIEW user_order_summary AS
    SELECT u.name, COUNT(o.id) AS order_count
    FROM users u
    JOIN orders o ON o.user_id = u.id
    GROUP BY u.id;

CREATE FUNCTION get_user_name(user_id INTEGER) RETURNS TEXT AS $$
BEGIN
    RETURN (SELECT name FROM users WHERE id = user_id);
END;
$$ LANGUAGE plpgsql;
