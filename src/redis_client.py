import redis
from .settings import env

redis_cnn = redis.Redis(host=env.get('redis_host', 'localhost'), port=env.get('redis_port', 6379), decode_responses=True)