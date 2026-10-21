"""Provide API adapters over one process-local fakeredis session store.

Local Redis wrappers are loaded by file path because the installed ``redis``
package shadows the source directory. Dependency factories create lightweight
adapters but share the same underlying client for conversation turns, routine
drafts, and session metadata; none of this state survives a process restart.
"""

import importlib.util
from pathlib import Path as FilePath

_REDIS_DIR = FilePath(__file__).resolve().parents[1] / "redis"


def _load(module_name: str, file: FilePath):
    """Execute a local wrapper module without importing the installed package.

    Args:
        module_name (str): Name assigned to the dynamically loaded module.
        file (FilePath): Path to the local Python source file.

    Returns:
        types.ModuleType: Executed module exposing the requested wrapper.

    Raises:
        OSError: If source loading fails.
        ImportError: If executing a wrapper cannot import a dependency.
        AttributeError: If a usable module specification or loader is absent.
    """
    # 1. Bypass the package-name collision while retaining normal module execution.
    spec = importlib.util.spec_from_file_location(module_name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RedisClient = _load("local_redis_client", _REDIS_DIR / "RedisClient.py").RedisClient
SetKey = _load("local_redis_set_key", _REDIS_DIR / "funcs" / "SetKey.py").SetKey
SetTurn = _load("local_redis_set_turn", _REDIS_DIR / "funcs" / "SetTurn.py").SetTurn
GetNTurns = _load("local_redis_get_n_turns", _REDIS_DIR / "funcs" / "GetNTurns.py").GetNTurns

# 1. Keep all endpoint adapters on one store so draft and memory scopes agree.
_redis_client = RedisClient()


def get_set_key() -> SetKey:
    """Build the session-initialization adapter for FastAPI injection.

    Returns:
        SetKey: Adapter using the process-wide session client.
    """
    # 1. Initialize metadata in the same store used by chat and routine drafts.
    return SetKey(_redis_client)


def get_set_turn() -> SetTurn:
    """Build the conversation-write adapter for pipeline and save endpoints.

    Returns:
        SetTurn: Adapter appending successful turns to shared session memory.
    """
    # 1. Route conversation writes to the process-wide session store.
    return SetTurn(_redis_client)


def get_n_turns() -> GetNTurns:
    """Build the recent-history adapter consumed by the chat pipeline.

    Returns:
        GetNTurns: Adapter reading ordered turns from the shared session store.
    """
    # 1. Read routing context from the same store that receives successful turns.
    return GetNTurns(_redis_client)


def get_routine_store() -> RedisClient:
    """Expose the shared routine-state and session-reset dependency.

    Returns:
        RedisClient: Existing process-wide client, not a fresh store.
    """
    # 1. Preserve shared draft state across independently injected endpoint adapters.
    return _redis_client
