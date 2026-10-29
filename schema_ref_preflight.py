"""Bounded local-reference preflight, not a JSON Schema validator. Python 3.11+."""

import argparse
import json
import math
import os
import re
import sys
from urllib.parse import unquote_to_bytes, urlsplit

MAPS = frozenset(("$defs", "properties", "patternProperties", "dependentSchemas"))
LISTS = frozenset(("allOf", "anyOf", "oneOf", "prefixItems"))
SINGLES = frozenset(("items", "additionalProperties", "contains", "propertyNames",
                     "not", "if", "then", "else", "unevaluatedProperties",
                     "unevaluatedItems", "contentSchema"))
DIALECT = "https://json-schema.org/draft/2020-12/schema"
VOCABS = frozenset("https://json-schema.org/draft/2020-12/vocab/" + name for name in
                   ("core", "applicator", "validation", "unevaluated", "meta-data",
                    "format-annotation", "content"))
URI_FRAGMENT = re.compile(r"[A-Za-z0-9._~!$&'()*+,;=:@/?%\-]*\Z")
BAD_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")
INDEX = re.compile(r"(?:0|[1-9][0-9]*)\Z")


class InputProblem(Exception):
    def __init__(self, code):
        self.code = code


def finding(code, source="", target=None):
    item = {"code": code, "source": source}
    if target is not None:
        item["target"] = target
    return item


def result(findings, schemas=0, refs=0):
    findings.sort(key=lambda item: (item["source"], item["code"], item.get("target", "")))
    code = 2 if any(not item["code"].startswith("REF_DANGLING") and
                    item["code"] != "REF_TARGET_NOT_SCHEMA" for item in findings) else int(bool(findings))
    return {"exit_code": code, "schema_nodes": schemas, "references": refs, "findings": findings}


def pointer(path):
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in path)


def no_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise InputProblem("INVALID_JSON")
        obj[key] = value
    return obj


def reject_constant(_value):
    raise InputProblem("INVALID_JSON")


def load_document(raw, max_nodes, max_depth):
    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates,
                              parse_constant=reject_constant)
    except RecursionError:
        raise InputProblem("LIMIT_DEPTH") from None
    except (ValueError, UnicodeError):
        raise InputProblem("INVALID_JSON") from None
    stack = [(document, 0)]
    count = 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > max_nodes:
            raise InputProblem("LIMIT_NODES")
        if depth > max_depth:
            raise InputProblem("LIMIT_DEPTH")
        if isinstance(node, float) and not math.isfinite(node):
            raise InputProblem("INVALID_JSON")
        strings = list(node) if isinstance(node, dict) else [node] if isinstance(node, str) else []
        if any(any(0xD800 <= ord(char) <= 0xDFFF for char in value) for value in strings):
            raise InputProblem("INVALID_JSON")
        if isinstance(node, dict):
            stack.extend((value, depth + 1) for value in node.values())
        elif isinstance(node, list):
            stack.extend((value, depth + 1) for value in node)
    return document


def decode_reference(ref):
    if not ref.startswith("#"):
        raise InputProblem("UNSUPPORTED_REF")
    fragment = ref[1:]
    if not URI_FRAGMENT.fullmatch(fragment) or BAD_PERCENT.search(fragment):
        raise InputProblem("REF_SYNTAX")
    try:
        decoded = unquote_to_bytes(fragment).decode("utf-8", errors="strict")
    except (UnicodeError, ValueError):
        raise InputProblem("REF_SYNTAX") from None
    if not decoded:
        return ()
    if not decoded.startswith("/"):
        raise InputProblem("UNSUPPORTED_REF")
    tokens = decoded[1:].split("/")
    if any(re.search(r"~(?![01])", token) for token in tokens):
        raise InputProblem("REF_SYNTAX")
    return tuple(token.replace("~1", "/").replace("~0", "~") for token in tokens)


def resolve(document, tokens):
    node = document
    for token in tokens:
        if isinstance(node, dict) and token in node:
            node = node[token]
        elif isinstance(node, list) and INDEX.fullmatch(token):
            # Compare before int(): huge hostile indices need no conversion.
            bound = str(len(node))
            if len(token) > len(bound) or (len(token) == len(bound) and token >= bound):
                raise InputProblem("REF_DANGLING")
            node = node[int(token)]
        else:
            raise InputProblem("REF_DANGLING")
    return node


def safe_root_id(value):
    if not isinstance(value, str) or not value or BAD_PERCENT.search(value):
        return False
    if any(ord(char) <= 32 or ord(char) >= 127 for char in value) or "#" in value:
        return False
    if any(char in value for char in '<>"{}|\\^`'):
        return False
    try:
        urlsplit(value)
    except ValueError:
        return False
    return True


def inspect(document, max_refs):
    findings, refs, schemas = [], [], set()
    stack = [(document, ())]
    while stack:
        node, path = stack.pop()
        if not isinstance(node, (dict, bool)):
            findings.append(finding("INVALID_SCHEMA", pointer(path)))
            continue
        schemas.add(path)
        if isinstance(node, bool):
            continue
        for keyword in sorted(node):
            value = node[keyword]
            location = path + (keyword,)
            source = pointer(location)
            if keyword == "$schema" and value != DIALECT:
                findings.append(finding("UNSUPPORTED_DIALECT", source))
            elif keyword in ("$anchor", "$dynamicAnchor", "$dynamicRef") or (keyword == "$id" and path):
                findings.append(finding("UNSUPPORTED_SCOPE", source))
            elif keyword == "$id" and not safe_root_id(value):
                findings.append(finding("UNSUPPORTED_SCOPE", source))
            elif keyword == "$vocabulary":
                if not isinstance(value, dict) or any(not isinstance(flag, bool) for flag in value.values()):
                    findings.append(finding("INVALID_KEYWORD", source))
                elif any(uri not in VOCABS for uri in value):
                    findings.append(finding("UNSUPPORTED_VOCABULARY", source))
            elif keyword == "$ref":
                if not isinstance(value, str):
                    findings.append(finding("INVALID_KEYWORD", source))
                else:
                    refs.append((location, value))
                    if len(refs) > max_refs:
                        return result([finding("LIMIT_REFS", source)], len(schemas), len(refs))
            elif keyword in MAPS:
                if not isinstance(value, dict):
                    findings.append(finding("INVALID_KEYWORD", source))
                else:
                    for key, child in value.items():
                        if not isinstance(child, (dict, bool)):
                            findings.append(finding("INVALID_KEYWORD", pointer(location + (key,))))
                        else:
                            stack.append((child, location + (key,)))
            elif keyword in LISTS:
                if not isinstance(value, list):
                    findings.append(finding("INVALID_KEYWORD", source))
                else:
                    for index, child in enumerate(value):
                        if not isinstance(child, (dict, bool)):
                            findings.append(finding("INVALID_KEYWORD", pointer(location + (str(index),))))
                        else:
                            stack.append((child, location + (str(index),)))
            elif keyword in SINGLES:
                if not isinstance(value, (dict, bool)):
                    findings.append(finding("INVALID_KEYWORD", source))
                else:
                    stack.append((value, location))
    for path, ref in refs:
        target = None
        try:
            tokens = decode_reference(ref)
            target = pointer(tokens)
            resolve(document, tokens)
            if tokens not in schemas:
                raise InputProblem("REF_TARGET_NOT_SCHEMA")
        except InputProblem as problem:
            findings.append(finding(problem.code, pointer(path), target))
    return result(findings, len(schemas), len(refs))


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise InputProblem("INVALID_ARGUMENTS")


def positive(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("positive integer required") from None
    if not 1 <= number <= 1_000_000_000:
        raise argparse.ArgumentTypeError("positive bounded integer required")
    return number


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument("file", help="UTF-8 schema JSON file; no network or reference file access")
    parser.add_argument("--json", action="store_true", help="deterministic machine-readable report")
    parser.add_argument("--max-bytes", type=positive, default=1_048_576)
    parser.add_argument("--max-nodes", type=positive, default=100_000)
    parser.add_argument("--max-depth", type=positive, default=128)
    parser.add_argument("--max-refs", type=positive, default=10_000)
    json_output = "--json" in (sys.argv[1:] if argv is None else argv)
    try:
        args = parser.parse_args(argv)
        with open(args.file, "rb") as stream:
            raw = stream.read(args.max_bytes + 1)
        if len(raw) > args.max_bytes:
            raise InputProblem("LIMIT_BYTES")
        document = load_document(raw, args.max_nodes, args.max_depth)
        report = inspect(document, args.max_refs)
    except InputProblem as problem:
        report = result([finding(problem.code)])
    except OSError:
        report = result([finding("IO_ERROR")])
    except (MemoryError, RecursionError):
        report = result([finding("RESOURCE_ERROR")])
    if json_output:
        print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    else:
        print("schema-ref-preflight: exit={exit_code} schemas={schema_nodes} refs={references}".format(**report))
        for item in report["findings"]:
            # JSON quoting keeps property-name control characters on one line.
            print(json.dumps(item, ensure_ascii=True, sort_keys=True))
    return report["exit_code"]


def entrypoint():
    try:
        try:
            status = main()
        except SystemExit as stopped:
            status = stopped.code
        sys.stdout.flush()
        return status
    except OSError:
        # Redirect the descriptor as well to prevent shutdown-flush diagnostics.
        try:
            with open(os.devnull, "w") as sink:
                os.dup2(sink.fileno(), sys.stdout.fileno())
        except OSError:
            pass
        return 2


if __name__ == "__main__":
    sys.exit(entrypoint())
