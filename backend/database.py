from sqlalchemy import create_engine, text
from config import DB_CONFIG, cprint


db_uri = (
    f"mysql+mysqlconnector://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}/{DB_CONFIG['database']}?connect_timeout=3"
)
try:
    db_engine = create_engine(db_uri)
    with db_engine.connect():
        cprint("db", f"Connected: {DB_CONFIG['database']}")
except Exception as e:
    cprint("db", f"Connection error: {e}")
    db_engine = None


def ensure_auth_schema() -> None:
    if not db_engine:
        return
    with db_engine.begin() as conn:
        conn.execute(text("""
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
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                token VARCHAR(255) NOT NULL UNIQUE,
                used_at DATETIME NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_invitations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(150) NOT NULL UNIQUE,
                company_name VARCHAR(150) DEFAULT '',
                department VARCHAR(100) DEFAULT '',
                invited_by INT NULL,
                invitation_token VARCHAR(255) NOT NULL UNIQUE,
                status ENUM('pending', 'accepted', 'expired', 'revoked') DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (invited_by) REFERENCES users(id) ON DELETE SET NULL
            )
        """))
        invitation_columns = conn.execute(text("SHOW COLUMNS FROM user_invitations LIKE 'department'"))
        if not invitation_columns.fetchone():
            conn.execute(text("ALTER TABLE user_invitations ADD COLUMN department VARCHAR(100) DEFAULT ''"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS password_reset_requests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                status ENUM('requested', 'issued', 'completed', 'cancelled') DEFAULT 'requested',
                requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                handled_by INT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (handled_by) REFERENCES users(id) ON DELETE SET NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS auth_otp_challenges (
                id INT AUTO_INCREMENT PRIMARY KEY,
                purpose VARCHAR(20) NOT NULL,
                subject_id INT NOT NULL,
                challenge_key VARCHAR(80) NOT NULL UNIQUE,
                email VARCHAR(150) NOT NULL,
                otp_hash CHAR(64) NOT NULL,
                attempts INT NOT NULL DEFAULT 0,
                expires_at DATETIME NOT NULL,
                resend_after DATETIME NOT NULL,
                verified_at DATETIME NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uq_auth_otp_subject (purpose, subject_id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_tokens (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL UNIQUE,
                tokens INT DEFAULT 0,
                last_updated DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """))
        user_lifecycle_columns = {
            "account_status": "VARCHAR(20) NOT NULL DEFAULT 'active'",
            "account_expires_at": "DATETIME NULL",
            "account_expiry_mode": "VARCHAR(20) NOT NULL DEFAULT 'none'",
            "account_expiry_duration": "SMALLINT NULL",
            "account_expiry_unit": "VARCHAR(10) NULL",
            "password_policy_type": "VARCHAR(20) NOT NULL DEFAULT 'none'",
            "password_policy_months": "SMALLINT NULL",
            "password_policy_day": "TINYINT NULL",
            "password_policy_repeat": "VARCHAR(10) NOT NULL DEFAULT 'once'",
            "password_policy_interval": "SMALLINT NULL",
            "password_policy_unit": "VARCHAR(10) NULL",
            "password_policy_on": "TINYINT NULL",
            "password_policy_month": "TINYINT NULL",
            "password_policy_date": "DATETIME NULL",
            "password_policy_anchor": "DATE NULL",
            "password_policy_schedule": "TEXT NULL",
            "password_expires_at": "DATETIME NULL",
        }
        for column, definition in user_lifecycle_columns.items():
            exists = conn.execute(text(f"SHOW COLUMNS FROM users LIKE '{column}'")).fetchone()
            if not exists:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {column} {definition}"))
        conn.execute(text("""
            UPDATE users
            SET password_policy_interval=password_policy_months,
                password_policy_unit='month'
            WHERE password_policy_type='duration' AND password_policy_interval IS NULL
        """))
        conn.execute(text("""
            UPDATE users
            SET password_policy_type='date', password_policy_repeat='repeat',
                password_policy_interval=CASE WHEN password_policy_type='even_months' THEN 2 ELSE 1 END,
                password_policy_unit='month', password_policy_on=password_policy_day,
                                password_policy_anchor=DATE(COALESCE(password_expires_at, NOW())),
                                password_policy_schedule=JSON_ARRAY(password_policy_day)
            WHERE password_policy_type IN ('monthly', 'even_months')
                            AND password_policy_schedule IS NULL
        """))
        conn.execute(text("""
            UPDATE users SET account_expiry_mode='date'
            WHERE account_expiry_mode='none' AND account_expires_at IS NOT NULL
        """))


try:
    ensure_auth_schema()
except Exception as e:
    cprint("db", f"Schema creation error: {e}")
