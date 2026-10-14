"""AI Visual Novel agent system with lazy public exports."""

from importlib import import_module


_EXPORTS = {
    "ProducerAgent": (".producer_agent", "ProducerAgent"),
    "ArtistAgent": (".artist_agent", "ArtistAgent"),
    "WriterAgent": (".writer_agent", "WriterAgent"),
    "ActorAgent": (".actor_agent", "ActorAgent"),
    "APIConfig": (".config", "APIConfig"),
    "PathConfig": (".config", "PathConfig"),
    "JSONParser": (".utils", "JSONParser"),
    "FileHelper": (".utils", "FileHelper"),
    "PromptBuilder": (".utils", "PromptBuilder"),
    "TextProcessor": (".utils", "TextProcessor"),
    "call_tool": (".tool_registry", "call_tool"),
    "list_available_tools": (".tool_registry", "list_available_tools"),
}


def __getattr__(name):
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value

__all__ = [
    'ProducerAgent',
    'ArtistAgent',
    'WriterAgent',
    'ActorAgent',
    'APIConfig',
    'PathConfig',
    'JSONParser',
    'FileHelper',
    'PromptBuilder',
    'TextProcessor',
    'call_tool',
    'list_available_tools'
]
