CREATE TABLE IF NOT EXISTS ADMINISTRATOR (
    AdminID TEXT PRIMARY KEY,
    Username TEXT NOT NULL UNIQUE,
    Status TEXT NOT NULL CHECK (Status IN ('active', 'inactive')),
    CreatedAt TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS "USER" (
    UserID TEXT PRIMARY KEY,
    AdminID TEXT NOT NULL,
    Name TEXT NOT NULL,
    FingerprintID INTEGER NOT NULL UNIQUE,
    Classification TEXT NOT NULL CHECK (Classification IN ('Cartoonist', 'Writer', 'Photojournalist')),
    Status TEXT NOT NULL CHECK (Status IN ('active', 'inactive')) DEFAULT 'active',
    EnrollmentStatus TEXT NOT NULL CHECK (EnrollmentStatus IN ('pending', 'enrolled')) DEFAULT 'pending',
    CreatedAt TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (AdminID) REFERENCES ADMINISTRATOR(AdminID) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS ATTENDANCE_LOG (
    LogID TEXT PRIMARY KEY,
    UserID TEXT NOT NULL,
    Date TEXT NOT NULL,
    TimeIn TEXT NOT NULL,
    TimeOut TEXT,
    Duration INTEGER,
    SyncStatus TEXT NOT NULL CHECK (SyncStatus IN ('pending', 'synced', 'failed')) DEFAULT 'pending',
    CreatedAt TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (UserID) REFERENCES "USER"(UserID) ON UPDATE CASCADE ON DELETE RESTRICT,
    CHECK (TimeOut IS NULL OR TimeOut >= TimeIn),
    CHECK (Duration IS NULL OR Duration >= 0),
    CHECK ((TimeOut IS NULL AND Duration IS NULL) OR (TimeOut IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_user_admin ON "USER" (AdminID);
CREATE INDEX IF NOT EXISTS idx_user_classification ON "USER" (Classification);
CREATE INDEX IF NOT EXISTS idx_attendance_user_date ON ATTENDANCE_LOG (UserID, Date);
CREATE INDEX IF NOT EXISTS idx_attendance_syncstatus ON ATTENDANCE_LOG (SyncStatus);
CREATE UNIQUE INDEX IF NOT EXISTS idx_attendance_one_open_session ON ATTENDANCE_LOG(UserID) WHERE TimeOut IS NULL;
