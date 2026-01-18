Traceback (most recent call last):
  File "/Users/yyhdbl/Documents/agent/Nihil/MyCodeAgent/scripts/chat_test_agent.py", line 35, in <module>
    from agents.codeAgent import CodeAgent
  File "/Users/yyhdbl/Documents/agent/Nihil/MyCodeAgent/agents/__init__.py", line 1, in <module>
    from .codeAgent import CodeAgent
  File "/Users/yyhdbl/Documents/agent/Nihil/MyCodeAgent/agents/codeAgent.py", line 14, in <module>
    from core.context_engine.trace_logger import create_trace_logger
  File "/Users/yyhdbl/Documents/agent/Nihil/MyCodeAgent/core/context_engine/trace_logger.py", line 20, in <module>
    from core.context_engine.trace_sanitizer import TraceSanitizer
  File "/Users/yyhdbl/Documents/agent/Nihil/MyCodeAgent/core/context_engine/trace_sanitizer.py", line 9, in <module>
    class TraceSanitizer:
  File "/Users/yyhdbl/Documents/agent/Nihil/MyCodeAgent/core/context_engine/trace_sanitizer.py", line 35, in TraceSanitizer
    (re.compile(r"Bearer\\s+[a-zA-Z0-9._\\-+/=]{20,}"), "Bearer ***"),
     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/yyhdbl/.local/share/uv/python/cpython-3.11.14-macos-aarch64-none/lib/python3.11/re/__init__.py", line 227, in compile
    return _compile(pattern, flags)
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/yyhdbl/.local/share/uv/python/cpython-3.11.14-macos-aarch64-none/lib/python3.11/re/__init__.py", line 294, in _compile
    p = _compiler.compile(pattern, flags)
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/yyhdbl/.local/share/uv/python/cpython-3.11.14-macos-aarch64-none/lib/python3.11/re/_compiler.py", line 745, in compile
    p = _parser.parse(p, flags)
        ^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/yyhdbl/.local/share/uv/python/cpython-3.11.14-macos-aarch64-none/lib/python3.11/re/_parser.py", line 989, in parse
    p = _parse_sub(source, state, flags & SRE_FLAG_VERBOSE, 0)
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/yyhdbl/.local/share/uv/python/cpython-3.11.14-macos-aarch64-none/lib/python3.11/re/_parser.py", line 464, in _parse_sub
    itemsappend(_parse(source, state, verbose, nested + 1,
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/yyhdbl/.local/share/uv/python/cpython-3.11.14-macos-aarch64-none/lib/python3.11/re/_parser.py", line 621, in _parse
    raise source.error(msg, len(this) + 1 + len(that))
re.error: bad character range \\-+ at position 22