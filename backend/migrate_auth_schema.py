import mysql.connector

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "dummy_db",
}

SQL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS user_profiles (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL UNIQUE,
        first_name VARCHAR(100) DEFAULT '',
        last_name VARCHAR(100) DEFAULT '',
        company_name VARCHAR(150) DEFAULT '',
        department VARCHAR(100) DEFAULT '',
        phone VARCHAR(50) DEFAULT '',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        token VARCHAR(255) NOT NULL UNIQUE,
        expires_at DATETIME NOT NULL,
        used_at DATETIME NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_invitations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        email VARCHAR(150) NOT NULL UNIQUE,
        company_name VARCHAR(150) DEFAULT '',
        department VARCHAR(100) DEFAULT '',
        invited_by INT NULL,
        invitation_token VARCHAR(255) NOT NULL UNIQUE,
        expires_at DATETIME NOT NULL,
        status ENUM('pending', 'accepted', 'expired', 'revoked') DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (invited_by) REFERENCES users(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS password_reset_requests (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        status ENUM('requested', 'issued', 'completed', 'cancelled') DEFAULT 'requested',
        requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        handled_by INT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (handled_by) REFERENCES users(id) ON DELETE SET NULL
    )
    """,
]


def main():
    conn = mysql.connector.connect(**DB_CONFIG)
    cur = conn.cursor()
    for stmt in SQL_STATEMENTS:
        cur.execute(stmt)
    cur.execute("SHOW COLUMNS FROM user_invitations LIKE 'department'")
    if not cur.fetchone():
        cur.execute("ALTER TABLE user_invitations ADD COLUMN department VARCHAR(100) DEFAULT ''")
    conn.commit()
    cur.execute("SHOW TABLES")
    tables = [row[0] for row in cur.fetchall()]
    print("TABLES:", tables)
    print("new auth schema created successfully")
    conn.close()


if __name__ == "__main__":
    main()
