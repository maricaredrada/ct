from app.config import Config
from app.db import init_db

if __name__ == "__main__":
    cfg = Config()
    init_db(cfg.DATABASE_PATH)
    print(f"Initialized database at {cfg.DATABASE_PATH}")
