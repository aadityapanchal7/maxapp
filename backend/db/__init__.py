"""Database package"""
from .sqlalchemy import get_db, init_db, close_db, engine, AsyncSessionLocal, release_conn
from .rds import get_rds_db, get_rds_db_optional, init_rds_db, close_rds_db, rds_engine, RDSSessionLocal
from .tx import best_effort

# Backward compatibility (old name)
get_database = get_db
