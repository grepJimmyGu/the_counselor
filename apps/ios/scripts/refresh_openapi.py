#!/usr/bin/env python3
"""Refresh LivermoreKit's copy of the backend OpenAPI schema.

    python3 apps/ios/scripts/refresh_openapi.py --local      # from this checkout's backend code
    python3 apps/ios/scripts/refresh_openapi.py --local --check   # what CI runs
    python3 apps/ios/scripts/refresh_openapi.py              # from production
    python3 apps/ios/scripts/refresh_openapi.py --file x.json

Use `--local` when the backend change and the app change are in the same PR:
production does not have the new endpoint until the PR merges, which is how
the options endpoints came to be merged into this file by hand (#381).
`--local` imports the backend, so it needs the backend's pinned requirements;
it makes no network call and opens no database. The schema's shape depends on
the FastAPI version, so run it in an environment built from
`apps/api/requirements.txt`, not whatever Python happens to be on the machine:

    uv run --python 3.12 --with-requirements apps/api/requirements.txt \
        python apps/ios/scripts/refresh_openapi.py --local

`--check` writes nothing. It fails if the checked-in file no longer describes
the paths the app uses (the `filter.paths` list in
`openapi-generator-config.yaml`) the way the backend code does. Only those
paths and the schemas they reach are compared, so a backend change the app
never calls does not ask anyone to touch this file.

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
import os
import pathlib
import re
import sys
import urllib.request

DEFAULT_URL = "https://thecounselor-production.up.railway.app/openapi.json"
IOS = pathlib.Path(__file__).resolve().parent.parent
OUT = IOS / "LivermoreKit/Sources/LivermoreAPI/openapi.json"
GENERATOR_CONFIG = OUT.parent / "openapi-generator-config.yaml"
API_ROOT = IOS.parent / "api"
SCHEMA_REF = "#/components/schemas/"


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


def local_schema() -> dict:
    """The schema of the backend code in this checkout. No server, no database."""
    sys.path.insert(0, str(API_ROOT))
    os.environ.setdefault("NEXTAUTH_SECRET", "schema-export-not-a-real-secret")
    # The signal routes are mounted only when this flag is on. It is on in
    # production and the app calls them, so the schema has to include them.
    os.environ["SIGNAL_ALERTS_ENABLED"] = "true"
    from app.main import app  # noqa: E402 - needs the path set above

    return app.openapi()


def used_paths() -> list:
    """The paths the app's client is generated for: `filter.paths` in the generator config."""
    return re.findall(r"^\s+-\s+(/\S+)\s*$", GENERATOR_CONFIG.read_text(), flags=re.MULTILINE)


def _refs(node, found: set) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(SCHEMA_REF):
            found.add(ref[len(SCHEMA_REF):])
        for value in node.values():
            _refs(value, found)
    elif isinstance(node, list):
        for value in node:
            _refs(value, found)


def contract(doc: dict, paths: list) -> dict:
    """What the app depends on: the used paths and every schema they reach."""
    schemas = doc.get("components", {}).get("schemas", {})
    picked = {path: doc.get("paths", {}).get(path) for path in paths}
    reached, queue = set(), set()
    _refs(picked, queue)
    while queue:
        name = queue.pop()
        if name in reached:
            continue
        reached.add(name)
        _refs(schemas.get(name), queue)
    return {"paths": picked, "schemas": {name: schemas.get(name) for name in sorted(reached)}}


def differences(checked_in: dict, current: dict, paths: list) -> list:
    """One line per used path or schema where the file and the backend disagree."""
    have, want = contract(checked_in, paths), contract(current, paths)
    lines = []
    for kind in ("paths", "schemas"):
        for name in sorted(set(have[kind]) | set(want[kind])):
            old, new = have[kind].get(name), want[kind].get(name)
            if old == new:
                continue
            if new is None:
                lines.append(f"{kind[:-1]} {name}: the app uses it, the backend no longer has it")
            elif old is None:
                lines.append(f"{kind[:-1]} {name}: in the backend, missing from openapi.json")
            else:
                lines.append(f"{kind[:-1]} {name}: differs")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    source = ap.add_mutually_exclusive_group()
    source.add_argument("--url", default=DEFAULT_URL)
    source.add_argument("--file", help="read a local schema instead of fetching")
    source.add_argument("--local", action="store_true",
                        help="build the schema from this checkout's backend code")
    ap.add_argument("--check", action="store_true",
                    help="write nothing; fail if openapi.json is out of date for the paths the app uses")
    args = ap.parse_args()

    if args.local:
        doc = local_schema()
    elif args.file:
        doc = json.loads(pathlib.Path(args.file).read_text())
    else:
        with urllib.request.urlopen(args.url, timeout=60) as resp:
            doc = json.load(resp)

    rewritten = normalize(doc)

    if args.check:
        paths = used_paths()
        text = OUT.read_text()
        checked_in = json.loads(text)
        drift = differences(checked_in, doc, paths)
        # The generated Swift initialisers take their arguments in the order
        # the file lists a schema's fields, so a hand-merged, unsorted block
        # compiles today and breaks call sites at the next real refresh.
        if text != json.dumps(checked_in, indent=1, sort_keys=True) + "\n":
            drift.append("the file is not in this script's format (sorted keys, 1-space indent): it was edited by hand")
        if drift:
            print(f"openapi.json is out of date for {len(drift)} of the things the app uses:")
            for line in drift:
                print(f"  - {line}")
            print("\nFix: python3 apps/ios/scripts/refresh_openapi.py --local   (then build the app)")
            sys.exit(1)
        print(f"openapi.json matches the backend for the {len(paths)} paths the app uses")
        return

    OUT.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print(f"{OUT.relative_to(OUT.parents[4])}: {len(doc['paths'])} paths, "
          f"{len(doc['components']['schemas'])} schemas, {rewritten} nullable fields rewritten")


if __name__ == "__main__":
    main()
