# Testing

Local environment: Windows, Python 3.11.15, standard library only. Test date:
2026-10-29. No external validator or network is required for these tests.

```console
python -m unittest discover -s tests -v
```

## Actual development evidence

1. Wrote subprocess tests before implementation. The initial CLI stub always
   returned an empty clean report.
2. Ran the dangling-reference test in isolation: **1 test, 1 failure**. It
   expected exit 1 for `#/$defs/missing` and actually got 0. This was a behavior
   assertion failure, not an import or dependency error.
3. Implemented the supported subset. The first full implementation run found
   two failures: Windows closed stdout raised `OSError: [Errno 22]`; one array
   test had used an unencoded Unicode character in a URI. Updated the latter
   to its percent-encoded form so it tests array-index rules after URI decoding.
4. Fixed output handling, including argparse `--help`'s `SystemExit`, explicit
   flushing, and descriptor redirection on output failure. Full suite:
   **29 tests passed**.
5. A later clean-venv controller run in a deeper disposable directory exceeded
   its 150-second suite limit. A four-case timing probe on the same interpreter
   and input measured original-directory relative/absolute script arguments at
   0.078/0.093 seconds, and disposable-directory relative/absolute arguments at
   0.079/4.046 seconds. Each returned the correct result and empty stderr.
   This demonstrates a path/launch configuration slowdown on this host, not
   its underlying OS cause. Tests now pass the script basename with explicit
   repository cwd and use 15-second subprocess timeouts. Context-managed pipe
   handles also remove the ResourceWarning visible in the clean environment.
   Product code was unchanged by this test-harness adjustment.
6. Re-ran all 29 tests using the clean venv: original directory **8.228 seconds**,
   disposable directory **8.146 seconds**, both passing without ResourceWarnings.
   All nine example/configuration checks also passed in the disposable copy.

Raw local builder logs are retained outside the publishable repository in the
batch's `builder-evidence/schema-ref-preflight/` directory (`red-focused.txt`,
`red.txt`, `green.txt`, `diagnose-subprocess.txt`). The broad initial stub run had 22 failures and one
missing-output-field error; the focused red above is the decisive evidence.

## Coverage and limits

The suite executes real child processes and temporary input files. It covers
all recognized schema-bearing positions, annotations ignored, non-schema
targets, root booleans, recursive references, percent decoding once, Unicode
percent escapes, strict tilde syntax, array indices, dangling refs, dialect and
scope refusal, unknown vocabularies, malformed containers, duplicates,
nonfinite numbers, UTF-8 byte bounds, node/depth/reference limits, error-value
privacy, deterministic ordering, generic I/O/argument errors and closed pipes
for reports and help.

`checks.json` lists nine example/configuration commands with expected exit
statuses. A runner must prepend only the Python executable to each `args` list.
These are smoke checks in addition to the regression suite.

Passing these tests does not establish complete JSON Schema compliance, full
meta-schema validation, external resolution compatibility, instance validation,
performance on large production schemas, or execution on every OS/Python.
