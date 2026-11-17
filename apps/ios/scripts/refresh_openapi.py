#!/usr/bin/env python3
"""Refresh LivermoreKit's copy of the backend OpenAPI schema.

    python3 apps/ios/scripts/refresh_openapi.py              # from production
    python3 apps/ios/scripts/refresh_openapi.py --file x.json

Why this is not a plain download: FastAPI (Pydantic v2) writes every
`Optional[T]` field as `anyOf: [T, {"type": "null"}]`. swift-openapi-generator
does not support the `null` schema and *skips the whole property* with only a
build warning — so `UserPublic` came out with 2 of its 5 fields and every
nullable column on every response would have vanished the same way.

The fix is to rewrite each such field to plain `T` and drop it from the
object's `required` list. In Swift that is `T?`, which decodes both a missing
key and an explicit `null` — exactly what the API sends.

`OpenAPISchemaTests` fails if a `null` schema is ever left in the checked-in
file, so a refresh that bypasses this script cannot land silently.
"""
import argparse
import json
import pathlib
import urllib.request

DEFAULT_URL = "https://thecounselor-production.up.railway.app/openapi.json"
OUT = pathlib.Path(__file__).resolve().parent.parent / "LivermoreKit/Sources/LivermoreAPI/openapi.json"


def _is_null(schema) -> bool:
    return isinstance(schema, dict) and schema.get("type") == "null"


def _unwrap_nullable(schema: dict) -> bool:
    """Rewrite `anyOf/oneOf: [T, null]` in place. Returns True if it was nullable."""
    nullable = False
    for key in ("anyOf", "oneOf"):
        members = schema.get(key)
        if not isinstance(members, list) or not any(_is_null(m) for m in members):
            continue
        nullable = True
        rest = [m for m in members if not _is_null(m)]
        if len(rest) == 1:
            del schema[key]
            for k, v in rest[0].items():
                schema.setdefault(k, v)
        else:
            schema[key] = rest
    if isinstance(schema.get("type"), list) and "null" in schema["type"]:
        nullable = True
        kinds = [t for t in schema["type"] if t != "null"]
        schema["type"] = kinds[0] if len(kinds) == 1 else kinds
    return nullable


def normalize(node) -> int:
    """Walk the document; returns how many nullable schemas were rewritten."""
    count = 0
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            for name, prop in props.items():
                if isinstance(prop, dict) and _unwrap_nullable(prop):
                    count += 1
                    required = node.get("required")
                    if isinstance(required, list) and name in required:
                        required.remove(name)
        if _unwrap_nullable(node):
            count += 1
        for value in node.values():
            count += normalize(value)
    elif isinstance(node, list):
        for value in node:
            count += normalize(value)
    return count


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--file", help="read a local schema instead of fetching")
    args = ap.parse_args()

    if args.file:
        doc = json.loads(pathlib.Path(args.file).read_text())
    else:
        with urllib.request.urlopen(args.url, timeout=60) as resp:
            doc = json.load(resp)

    rewritten = normalize(doc)
    OUT.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print(f"{OUT.relative_to(OUT.parents[4])}: {len(doc['paths'])} paths, "
          f"{len(doc['components']['schemas'])} schemas, {rewritten} nullable fields rewritten")


if __name__ == "__main__":
    main()
