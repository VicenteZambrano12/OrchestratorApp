import importlib.util
from pathlib import Path as FilePath

_REDIS_DIR = FilePath(__file__).resolve().parents[1] / "redis"


def _load(module_name: str, file: FilePath):
    # The local `redis` folder is shadowed by the installed redis package,
    # so local modules are loaded by file path.
    spec = importlib.util.spec_from_file_location(module_name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RedisClient = _load("local_redis_client", _REDIS_DIR / "RedisClient.py").RedisClient
SetKey = _load("local_redis_set_key", _REDIS_DIR / "funcs" / "SetKey.py").SetKey
SetTurn = _load("local_redis_set_turn", _REDIS_DIR / "funcs" / "SetTurn.py").SetTurn
GetNTurns = _load("local_redis_get_n_turns", _REDIS_DIR / "funcs" / "GetNTurns.py").GetNTurns

# Single process-wide store shared by every endpoint.
_redis_client = RedisClient()


def get_set_key() -> SetKey:
    return SetKey(_redis_client)


def get_set_turn() -> SetTurn:
    return SetTurn(_redis_client)


def get_n_turns() -> GetNTurns:
    return GetNTurns(_redis_client)
