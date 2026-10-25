"""A small, dependency-free JSONPath subset for resource match rules.

Supported: ``$`` (root), ``.key``, ``['key']`` / ``["key"]``, ``[n]`` (index), ``[*]`` / ``.*`` (all children)
and ``..key`` (recursive descent). Filters and slices are not supported.
"""
from __future__ import annotations

import re
from typing import Any

_TOKEN = re.compile(r"""
    \.\.(?P<deep>[A-Za-z_][\w-]*|\*)       # ..key / ..*
  | \.(?P<key>[A-Za-z_][\w-]*|\*)          # .key / .*
  | \[\s*(?P<idx>-?\d+)\s*\]               # [0]
  | \[\s*\*\s*\]                           # [*]
  | \[\s*(?P<q>['"])(?P<qkey>.*?)(?P=q)\s*\]  # ['key']
""", re.X)


class JsonPathError(ValueError):
    pass


def parse(expr: str) -> list[tuple[str, Any]]:
    expr = expr.strip()
    if not expr.startswith("$"):
        raise JsonPathError(f"JSONPath must start with '$': {expr!r}")
    steps: list[tuple[str, Any]] = []
    pos = 1
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m:
            raise JsonPathError(f"unsupported JSONPath syntax at {expr[pos:]!r} in {expr!r}")
        if m.group("deep") is not None:
            steps.append(("deep", m.group("deep")))
        elif m.group("key") is not None:
            steps.append(("child", m.group("key")))
        elif m.group("idx") is not None:
            steps.append(("index", int(m.group("idx"))))
        elif m.group("qkey") is not None:
            steps.append(("child", m.group("qkey")))
        else:
            steps.append(("child", "*"))
        pos = m.end()
    return steps


def _children(node: Any) -> list[Any]:
    if isinstance(node, dict):
        return list(node.values())
    if isinstance(node, list):
        return list(node)
    return []


def _descendants(node: Any) -> list[Any]:
    out = [node]
    for child in _children(node):
        out.extend(_descendants(child))
    return out


def values(data: Any, expr: str) -> list[Any]:
    nodes = [data]
    for kind, arg in parse(expr):
        nxt: list[Any] = []
        for node in nodes:
            if kind == "index":
                if isinstance(node, list) and -len(node) <= arg < len(node):
                    nxt.append(node[arg])
            elif kind == "child":
                if arg == "*":
                    nxt.extend(_children(node))
                elif isinstance(node, dict) and arg in node:
                    nxt.append(node[arg])
            else:  # deep
                for d in _descendants(node):
                    if arg == "*":
                        nxt.extend(_children(d))
                    elif isinstance(d, dict) and arg in d:
                        nxt.append(d[arg])
        nodes = nxt
    return nodes


def last_key(expr: str) -> str | None:
    """The final property name of an expression (used to ignore it when corroborating)."""
    for kind, arg in reversed(parse(expr)):
        if kind in ("child", "deep") and arg != "*":
            return str(arg)
    return None


def matches(data: Any, rules: dict[str, str]) -> bool:
    """True when every rule's expression yields at least one scalar equal to the expected value."""
    if not rules:
        return False
    for expr, expected in rules.items():
        found = [v for v in values(data, expr) if not isinstance(v, (dict, list))]
        if not any(str(v) == str(expected) for v in found):
            return False
    return True


def any_node_matches(data: Any, rules: dict[str, str]) -> bool:
    """For list responses: does any object in the document satisfy the rules (each object as ``$``)?"""
    return any(isinstance(n, dict) and matches(n, rules) for n in _descendants(data))
