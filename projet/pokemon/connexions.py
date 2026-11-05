import os
from functools import lru_cache

import psycopg
import redis
from pgvector.psycopg import register_vector
from pymongo import MongoClient
from pymongo.write_concern import WriteConcern
from .traces import CurseurTrace, EcouteMongo


@lru_cache
def base_mongo():
    client = MongoClient(
        os.getenv('MONGO_URI', 'mongodb://mongo1,mongo2,mongo3/?replicaSet=rs0'),
        serverSelectionTimeoutMS=4000, connectTimeoutMS=3000,
        event_listeners=[EcouteMongo()],
    )
    return client.get_database(os.getenv('POKEMON_DATABASE', 'pokemon'),
                               write_concern=WriteConcern(w='majority', wtimeout=5000))


@lru_cache
def client_redis():
    return redis.from_url(os.getenv('REDIS_URL', 'redis://redis:6379/0'),
                          decode_responses=True, socket_connect_timeout=0.5,
                          socket_timeout=0.5, retry_on_timeout=False)


def connexion_postgres(vector=True):
    connexion = psycopg.connect(
        os.getenv('POSTGRES_DSN', 'postgresql://nyc:nyc@postgres:5432/nyceats'),
        connect_timeout=3, autocommit=True, options='-c statement_timeout=10000',
        cursor_factory=CurseurTrace,
    )
    if vector:
        try:
            register_vector(connexion)
        except Exception:
            connexion.close()
            raise
    return connexion
