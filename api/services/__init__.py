"""API services package.

Submodules are loaded on demand, e.g. ``from api.services import auth_service``.
Avoid importing heavy optional stacks from this ``__init__`` so tests and minimal
environments do not require every transitive dependency at import time.
"""
