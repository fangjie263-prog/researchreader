"""Research Dictionary loader.

Provides the ResearchDictionary class with a normalize() interface
that maps query terms (including aliases) to canonical entity names.
"""

import os
import yaml
from typing import Any, Dict, List, Optional


class Entity:
    """Represents a single dictionary entity."""

    __slots__ = ('canonical', 'aliases', 'categories', 'enabled',
                 'priority', 'metadata')

    def __init__(self, canonical: str, aliases: List[str],
                 categories: Optional[List[str]] = None,
                 enabled: bool = True, priority: int = 5,
                 metadata: Optional[Dict[str, Any]] = None):
        self.canonical = canonical
        self.aliases = aliases
        self.categories = categories or []
        self.enabled = enabled
        self.priority = priority
        self.metadata = metadata or {}

    def __repr__(self) -> str:
        return f"Entity({self.canonical!r})"


class ResearchDictionary:
    """Load and query the research entity dictionary."""

    KNOWN_FIELDS = frozenset([
        'canonical', 'aliases', 'categories',
        'enabled', 'priority', 'metadata',
    ])

    def __init__(self, path: Optional[str] = None):
        if path is None:
            _dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(_dir, 'entities.yaml')
        self._path = path
        self._alias_map: Dict[str, Entity] = {}
        self._entities: List[Entity] = []
        self._load()

    def _load(self) -> None:
        with open(self._path, 'r', encoding='utf-8') as f:
            content = f.read()
        for doc in yaml.safe_load_all(content):
            if doc is None or not isinstance(doc, dict):
                continue
            self._parse_entity(doc)

    def _parse_entity(self, raw: Dict[str, Any]) -> None:
        canonical = raw.get('canonical')
        aliases = raw.get('aliases', [])
        if not canonical or not isinstance(aliases, list):
            return
        entity = Entity(
            canonical=str(canonical),
            aliases=[str(a) for a in aliases],
            categories=raw.get('categories', []),
            enabled=bool(raw.get('enabled', True)),
            priority=int(raw.get('priority', 5)),
            metadata=raw.get('metadata', {}),
        )
        for alias in entity.aliases:
            self._alias_map[alias] = entity
        self._entities.append(entity)

    def normalize(self, query: str) -> List[Dict[str, Any]]:
        results = []
        matched = self._alias_map.get(query)
        if matched is not None:
            results.append({
                'canonical': matched.canonical,
                'matched_alias': query,
                'entity': matched,
            })
        return results
