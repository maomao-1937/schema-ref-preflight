import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "schema_ref_preflight.py"


class PreflightTests(unittest.TestCase):
    def run_raw(self, raw, *args):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "private-file.json"
            path.write_bytes(raw)
            result = subprocess.run([sys.executable, CLI.name, str(path), "--json", *args],
                                    cwd=ROOT, capture_output=True, text=True,
                                    encoding="utf-8", timeout=15)
        self.assertEqual(result.stderr, "")
        return result.returncode, json.loads(result.stdout)

    def run_schema(self, schema, *args):
        return self.run_raw(json.dumps(schema, ensure_ascii=False).encode("utf-8"), *args)

    def assert_code(self, schema, exit_code, code=None, *args):
        actual, report = self.run_schema(schema, *args)
        self.assertEqual(actual, exit_code, report)
        self.assertEqual(report["exit_code"], actual)
        if code:
            self.assertIn(code, [item["code"] for item in report["findings"]])
        return report

    def test_dangling_reference(self):
        report = self.assert_code({"$ref": "#/$defs/missing"}, 1, "REF_DANGLING")
        self.assertEqual(report["findings"][0]["source"], "/$ref")
        self.assertEqual(report["findings"][0]["target"], "/$defs/missing")

    def test_root_booleans(self):
        for value in [True, False]:
            self.assert_code(value, 0)

    def test_recursive_cycles_not_expanded(self):
        self.assert_code({"$defs": {"x": {"$ref": "#"}}, "$ref": "#/$defs/x"}, 0)

    def test_hash_is_root(self):
        self.assert_code({"$ref": "#"}, 0)

    def test_percent_and_pointer_escapes(self):
        schema = {"$defs": {"a/b~c 中文": False}, "$ref": "#/$defs/a~1b~0c%20%E4%B8%AD%E6%96%87"}
        self.assert_code(schema, 0)

    def test_percent_decoded_once(self):
        self.assert_code({"$defs": {"%2F": True}, "$ref": "#/$defs/%252F"}, 0)

    def test_invalid_percent_utf8_and_tilde(self):
        for ref in ["#/%", "#/%GG", "#/%FF", "#/~2", "#/~", "#/x#y", "#/a b"]:
            self.assert_code({"$ref": ref}, 2, "REF_SYNTAX")

    def test_canonical_array_indices(self):
        for token in ["01", "-", "+0", "%D9%A1", "999999999999999999999999999999999999999999"]:
            self.assert_code({"allOf": [True], "$ref": "#/allOf/" + token}, 1, "REF_DANGLING")
        self.assert_code({"allOf": [False], "$ref": "#/allOf/0"}, 0)

    def test_annotation_objects_are_not_schemas(self):
        for keyword in ["default", "const", "examples", "x-extension"]:
            self.assert_code({keyword: {"$ref": "other.json", "$id": "other"}}, 0)
            self.assert_code({keyword: {}, "$ref": "#/" + keyword}, 1, "REF_TARGET_NOT_SCHEMA")

    def test_all_schema_bearing_positions(self):
        maps = ["$defs", "properties", "patternProperties", "dependentSchemas"]
        lists = ["allOf", "anyOf", "oneOf", "prefixItems"]
        singles = ["items", "additionalProperties", "contains", "propertyNames", "not", "if", "then", "else", "unevaluatedProperties", "unevaluatedItems", "contentSchema"]
        for keyword in maps + lists + singles:
            child = {"$ref": "#/missing"}
            container = {"x": child} if keyword in maps else [child] if keyword in lists else child
            self.assert_code({keyword: container}, 1, "REF_DANGLING")

    def test_container_is_not_schema(self):
        self.assert_code({"properties": {}, "$ref": "#/properties"}, 1, "REF_TARGET_NOT_SCHEMA")

    def test_malformed_schema_containers(self):
        for schema in [{"properties": []}, {"allOf": {}}, {"items": []}, {"not": 1}, {"$defs": {"x": None}}, {"allOf": [1]}, {"$ref": 1}, {"$vocabulary": []}]:
            self.assert_code(schema, 2, "INVALID_KEYWORD")

    def test_invalid_root(self):
        for root in [1, None, [], "schema"]:
            self.assert_code(root, 2, "INVALID_SCHEMA")

    def test_dialect(self):
        self.assert_code({"$schema": "https://json-schema.org/draft/2020-12/schema"}, 0)
        self.assert_code({"$schema": "http://json-schema.org/draft-07/schema#"}, 2, "UNSUPPORTED_DIALECT")

    def test_scopes_and_anchors_hidden_in_real_subschemas(self):
        for key, value in [("$id", "child"), ("$anchor", "x"), ("$dynamicAnchor", "x"), ("$dynamicRef", "#x")]:
            self.assert_code({"$defs": {"x": {key: value}}}, 2, "UNSUPPORTED_SCOPE")

    def test_root_id_allowed_only_safe_shape(self):
        self.assert_code({"$id": "https://example.test/schema", "$ref": "#"}, 0)
        for value in ["#anchor", "https://example.test/schema#anchor", "bad uri", 3]:
            self.assert_code({"$id": value}, 2)

    def test_external_and_anchor_refs_unsupported(self):
        for ref in ["child.json", "https://example.test/schema", "#anchor", ""]:
            self.assert_code({"$ref": ref}, 2, "UNSUPPORTED_REF")

    def test_unknown_vocabulary_never_silently_clean(self):
        for required in [True, False]:
            self.assert_code({"$vocabulary": {"https://example.test/vocab": required}}, 2, "UNSUPPORTED_VOCABULARY")

    def test_duplicate_keys_and_nonfinite(self):
        for raw in [b'{"$ref":"#","$ref":"#/secret"}', b'{"default":NaN}', b'{"default":1e9999}']:
            actual, report = self.run_raw(raw)
            self.assertEqual(actual, 2)
            self.assertEqual(report["findings"][0]["code"], "INVALID_JSON")

    def test_invalid_json_does_not_echo_secret(self):
        for raw in [b'{"password":"super-secret",}', b'\xff']:
            actual, report = self.run_raw(raw)
            self.assertEqual(actual, 2)
            self.assertNotIn("super-secret", json.dumps(report))
            self.assertNotIn("private-file", json.dumps(report))

    def test_byte_bound_counts_utf8_bytes(self):
        raw = '{"title":"中文"}'.encode("utf-8")
        self.assertEqual(self.run_raw(raw, "--max-bytes", str(len(raw)))[0], 0)
        actual, report = self.run_raw(raw, "--max-bytes", str(len(raw) - 1))
        self.assertEqual(actual, 2)
        self.assertEqual(report["findings"][0]["code"], "LIMIT_BYTES")

    def test_nodes_include_annotation_values(self):
        self.assert_code({"default": [1, 2]}, 2, "LIMIT_NODES", "--max-nodes", "3")

    def test_depth_includes_annotations(self):
        self.assert_code({"default": {"x": {"y": 1}}}, 2, "LIMIT_DEPTH", "--max-depth", "2")

    def test_reference_limit(self):
        self.assert_code({"allOf": [{"$ref": "#"}, {"$ref": "#"}]}, 2, "LIMIT_REFS", "--max-refs", "1")

    def test_exit_two_takes_priority(self):
        self.assert_code({"$ref": "#/missing", "not": {"$anchor": "x"}}, 2, "REF_DANGLING")

    def test_deterministic_output_and_no_annotation_values(self):
        schema = {"properties": {"z": {"$ref": "#/missing"}, "a": {"$ref": "#/other"}}, "default": "SECRET"}
        first = self.run_schema(schema)
        self.assertEqual(first, self.run_schema(schema))
        self.assertNotIn("SECRET", json.dumps(first))
        self.assertEqual(first[1]["findings"][0]["source"], "/properties/a/$ref")

    def test_missing_input_generic_error(self):
        result = subprocess.run([sys.executable, CLI.name, str(ROOT / "SECRET-ABSOLUTE-MISSING")],
                                cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("SECRET", result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_invalid_arguments_do_not_echo_values(self):
        for args in [["--private-secret"], ["--max-depth", "secret-value"]]:
            result = subprocess.run([sys.executable, CLI.name, *args], cwd=ROOT,
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("secret", result.stdout + result.stderr)

    def test_closed_pipe_and_help_have_no_traceback(self):
        for args in [["--help"], [str(ROOT / "examples" / "clean.json")]]:
            with subprocess.Popen([sys.executable, CLI.name, *args], cwd=ROOT,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
                proc.stdout.close()
                # communicate must not attempt to read the already closed pipe.
                proc.stdout = None
                try:
                    _, error = proc.communicate(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=15)
                    raise
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(error, b"")
                self.assertNotIn(b"Traceback", error)
                self.assertNotIn(b"BrokenPipe", error)


if __name__ == "__main__":
    unittest.main()
