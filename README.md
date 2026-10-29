# schema-ref-preflight

[![tests](https://github.com/maomao-1937/schema-ref-preflight/actions/workflows/tests.yml/badge.svg)](https://github.com/maomao-1937/schema-ref-preflight/actions/workflows/tests.yml)

Find dangling local JSON Pointer references in one JSON Schema 2020-12 document,
before handing it to a full validator. Python 3.11+, standard library only.
No installation step, package downloads, or reference retrieval is needed.

This checks a deliberately small reference subset. A clean result means supported
local references point to recognized schema positions. It does **not** mean the
schema passes its meta-schema or any instance passes validation. For those jobs,
use mature tools such as [python-jsonschema](https://python-jsonschema.readthedocs.io/)
or [Sourcemeta JSON Schema CLI](https://github.com/sourcemeta/jsonschema).

## Quick start

Download the repository or copy `schema_ref_preflight.py`, then run:

```console
python schema_ref_preflight.py examples/clean.json
python schema_ref_preflight.py examples/dangling.json --json
python schema_ref_preflight.py examples/escaped.json --json
python -m unittest discover -s tests -v
```

The dangling example exits 1 and reports a stable code with source and target:

```json
{"exit_code": 1, "findings": [{"code": "REF_DANGLING", "source": "/properties/name/$ref", "target": "/$defs/lable"}], "references": 1, "schema_nodes": 3}
```

| Exit | Meaning |
| --- | --- |
| 0 | Clean within the supported subset |
| 1 | `REF_DANGLING` or `REF_TARGET_NOT_SCHEMA` |
| 2 | Invalid input, unsupported semantics, resource limit, I/O or argument error |

Exit 2 takes precedence over exit 1. Human and `--json` reports have deterministic
findings sorted by source, code, and target. JSON Pointer strings use `""` for the
root. Parsing and operational errors use generic codes without exception text.
`--help` exits 0 when stdout is usable; an output failure exits 2.

## Supported boundaries

- Missing `$schema` assumes 2020-12. The only explicit supported dialect URI is
  `https://json-schema.org/draft/2020-12/schema`.
- Object and boolean schemas are recognized at the root and these positions:
  `$defs`, `properties`, `patternProperties`, `dependentSchemas` map values;
  `allOf`, `anyOf`, `oneOf`, `prefixItems` list elements; and `items`,
  `additionalProperties`, `contains`, `propertyNames`, `not`, `if`, `then`, `else`,
  `unevaluatedProperties`, `unevaluatedItems`, `contentSchema` values.
- `$ref` accepts `#` and URI fragments that decode to `/...` JSON Pointers. It
  strictly checks URI fragment characters, percent escapes, UTF-8, `~0`/`~1`, and
  canonical ASCII array indices. Percent decoding happens once.
- Pointers resolve against the document, but targets must also be recognized
  object/boolean schema positions. Annotation data and map/list containers are
  rejected as targets, even if they happen to contain objects.
- References are checked without expansion; recursive schemas are accepted.
- A syntactically screened nonempty root `$id` without a fragment is accepted:
  local fragment references still address that root resource. Nested `$id`,
  `$anchor`, `$dynamicAnchor`, and `$dynamicRef` are unsupported, including inside
  unreferenced recognized subschemas. Root identifiers with any `#` are
  conservatively unsupported.
- External references, relative file references, empty references, and named
  anchor references return 2. Nothing is fetched; a reference URI is not treated
  as a filesystem path.
- `$vocabulary` accepts only the 2020-12 `core`, `applicator`, `validation`,
  `unevaluated`, `meta-data`, `format-annotation`, and `content` vocabulary URIs.
  Unknown vocabularies return 2 even when declared optional. `format-assertion`
  is unsupported.
- `default`, `const`, `examples`, and other unknown keyword values are data:
  their contents are not scanned for references or scopes. Custom keywords that
  introduce schemas need a different tool or an explicit future extension.
- Malformed known schema containers are rejected. This is not exhaustive
  meta-validation: for example, an empty `allOf` list and an invalid `type` value
  are outside this tool's assertions.

## Resource configuration and privacy

```console
python schema_ref_preflight.py examples/clean.json --json --max-bytes 1048576 --max-nodes 100000 --max-depth 128 --max-refs 10000
```

| Option | Default | Counts |
| --- | --- | --- |
| `--max-bytes` | 1,048,576 | Input bytes, including UTF-8 multibyte characters |
| `--max-nodes` | 100,000 | All parsed JSON values, including annotations; keys excluded |
| `--max-depth` | 128 | All value nesting, root depth 0; annotation nesting included |
| `--max-refs` | 10,000 | `$ref` strings at recognized schema nodes |

Options accept integers 1 through 1,000,000,000. Input reading is capped at the
byte limit plus one. JSON parsing precedes iterative node/depth checks; parser
recursion failures return `LIMIT_DEPTH`. These limits reduce accidental resource
use; this process is not a memory/time sandbox. Keep defaults or lower them for
untrusted documents. Duplicate JSON keys, NaN, Infinity, nonfinite numbers,
invalid UTF-8, and unpaired Unicode surrogates are rejected.

**Disclosure:** reports contain source and resolved target JSON Pointers.
Property names in those pointers may be sensitive. Reports omit full schema,
annotation and instance values, raw unsupported references, exception contents,
and absolute input paths. They do not hash or redact pointer names. Human
findings are JSON quoted to keep control characters on one line.

## 中文快速开始

这是单文件 JSON Schema 2020-12 本地 `$ref` 预检查工具。需要 Python 3.11 或更新版本，
只使用标准库，下载后即可运行，无需 `pip install`。

```console
python schema_ref_preflight.py examples/clean.json
python schema_ref_preflight.py examples/dangling.json --json
```

退出码：`0` 表示受支持范围内引用正常；`1` 表示引用不存在或指向非 Schema 位置；
`2` 表示输入错误、超出支持范围、超限或操作失败。它不会访问网络，也不会加载外部引用文件。

只扫描已列出的 Schema 位置，不把 `default`、`const`、`examples` 当作 Schema。
支持 `#`、本地 JSON Pointer、百分号 UTF-8 编码及递归引用；嵌套 `$id`、锚点、动态引用、
其他方言和未知词汇表会明确返回 `2`。通过预检查不等于完整 Schema 或实例校验通过。

默认限制为 1 MiB、100,000 个 JSON 值、128 层深度和 10,000 个引用；可用上表参数调整。
输出中的指针会暴露属性名称，请按实际敏感程度保管报告。

## Verification

Locally verified on Windows with Python 3.11.15. See [TESTING.md](TESTING.md) for
the actual red/green sequence and validation limits, [RESEARCH.md](RESEARCH.md)
for sources and the intended niche. No upstream implementation code was copied.
Licensed under MIT, copyright 2026 maomao-1937.
