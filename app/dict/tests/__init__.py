"""Add agents/ to import path for tests of offline LLM modules."""

import os
import sys

_AGENTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "agents",
)
if _AGENTS not in sys.path:
    sys.path.insert(0, _AGENTS)
