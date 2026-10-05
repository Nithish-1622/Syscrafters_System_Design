import os
import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

try:
    from .config import settings
except (ImportError, ValueError):
    from config import settings

DATABASE_URL = settings.DATABASE_URL

def get_resilient_engine():
    """Attempts PostgreSQL connection with fast-fail fallback to SQLite for local tests."""
    if DATABASE_URL.startswith("postgresql"):
        try:
            eng = create_engine(
                DATABASE_URL,
                pool_size=10,
                max_overflow=20,
                pool_timeout=3,
                connect_args={"connect_timeout": 3},
                echo=settings.SQL_ECHO
            )
            with eng.connect() as conn:
                pass
            return eng
        except Exception:
            return create_engine("sqlite:///./salestorm.db", connect_args={"check_same_thread": False})
    else:
        return create_engine(DATABASE_URL, echo=settings.SQL_ECHO)

engine = get_resilient_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_redis_client():
    try:
        client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.ping()
        return client
    except Exception:
        class MockRedis:
            def __init__(self):
                self._store = {}
                self._hashes = {}
                self._zset = {}
            def get(self, k): return self._store.get(k)
            def set(self, k, v, ex=None, nx=False):
                if nx and k in self._store: return False
                self._store[k] = str(v)
                return True
            def decrby(self, k, amount):
                v = int(self._store.get(k, 0)) - amount
                self._store[k] = str(v)
                return v
            def incrby(self, k, amount):
                v = int(self._store.get(k, 0)) + amount
                self._store[k] = str(v)
                return v
            def hset(self, name, key, value):
                if name not in self._hashes: self._hashes[name] = {}
                self._hashes[name][key] = str(value)
                return 1
            def hget(self, name, key):
                return self._hashes.get(name, {}).get(key)
            def hdel(self, name, key):
                if name in self._hashes and key in self._hashes[name]:
                    del self._hashes[name][key]
                    return 1
                return 0
            def hexists(self, name, key):
                return 1 if key in self._hashes.get(name, {}) else 0
            def zadd(self, name, mapping):
                if name not in self._zset: self._zset[name] = {}
                self._zset[name].update(mapping)
                return len(mapping)
            def zrangebyscore(self, name, min_score, max_score, start=0, num=100):
                items = [k for k, v in self._zset.get(name, {}).items() if float(min_score) <= float(v) <= float(max_score)]
                return items[start:start+num]
            def zrem(self, name, *keys):
                c = 0
                for k in keys:
                    if k in self._zset.get(name, {}):
                        del self._zset[name][k]
                        c += 1
                return c
            def eval(self, script, numkeys, *args):
                return 1
            def ping(self): return True
        return MockRedis()
