# Research and scope

Sources checked 2026-10-29. Implementation was written independently; no source
implementation code was copied.

## Facts from primary sources

- [JSON Schema 2020-12 Core](https://json-schema.org/draft/2020-12/json-schema-core),
  sections 4.3, 8.2, 9.2, 9.4 and 10: schemas can be objects or booleans;
  identifiers establish resource boundaries; references identify schemas;
  applicator keywords designate subschemas. References to non-schema locations
  require care, so an arbitrary object in annotation data is not assumed to be
  a schema here. Dynamic scope and embedded resources need more than raw
  document-pointer lookup.
- [RFC 6901](https://www.rfc-editor.org/rfc/rfc6901), sections 3, 4 and 6:
  pointer tokens escape tilde and slash; URI fragment representation also uses
  percent encoding. Array indices use ASCII digits without leading zeros.
  This tool decodes the URI layer once, then decodes pointer tokens, and rejects
  malformed escapes rather than repairing them.
- [Sourcemeta resolution guide](https://github.com/sourcemeta/jsonschema/blob/main/docs/guides/resolution.markdown):
  external resolution associates identifiers with schemas. A reference URI and
  a file's on-disk name are different concepts. This tool does not infer a file
  lookup from a URI; all nonfragment references produce an unsupported result.
- [python-jsonschema documentation](https://python-jsonschema.readthedocs.io/en/stable/):
  it implements JSON Schema validation and supports multiple drafts, including
  2020-12. Its API validates instances and offers structured validation errors.

## Product inference, not measured demand

A small no-dependency preflight may suit a CI step where teams want to catch
local reference typos without configuring a retrieval registry. That is a
hypothesis; no user interviews, adoption or time savings have been measured.
The value is predictable scope and small distribution size, not broader schema
correctness or superior compatibility.

## Alternatives and decision

| Alternative | Prefer it when |
| --- | --- |
| [python-jsonschema](https://python-jsonschema.readthedocs.io/) | You need full instance/meta-schema validation, Python integration, or multiple drafts |
| [Sourcemeta JSON Schema CLI](https://github.com/sourcemeta/jsonschema) | You need a mature CLI with broader validation, bundling and external resolution workflows |
| This script | You need only bounded local-pointer existence and recognized-target checks in one 2020-12 document |

The mature alternatives cover much more. This project does not claim a new
validation algorithm, benchmark advantage, or replacement for either tool.
