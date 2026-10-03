"""Standard-library tests. Run: python -m unittest discover -s scripts -p 'test_*.py'."""
import struct
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile

from compare_resource_blocks import ResourceError, compare, inspect_bytes, main


def resource(payloads):
    cursor = 16 + 12 * len(payloads)
    directory, body = bytearray(), bytearray()
    for index, (tag, payload) in enumerate(payloads):
        relative = cursor - (16 + 12 * index + 4)
        directory.extend(struct.pack("<4sII", tag.encode("ascii"), relative, len(payload)))
        body.extend(payload)
        cursor += len(payload)
    return struct.pack("<IHHII", cursor, 12, 1, 8, len(payloads)) + directory + body


class ResourceTests(unittest.TestCase):
    def test_same(self):
        info = inspect_bytes(resource([("DATA", b"body"), ("PHYS", b"physics")]))
        self.assertTrue(compare(info, info)["file_identical"])
        self.assertTrue(compare(info, info)["payload_allowlist_passed"])

    def test_duplicate_tags_not_lost(self):
        a = inspect_bytes(resource([("DATA", b"one"), ("DATA", b"two")]))
        b = inspect_bytes(resource([("DATA", b"one"), ("DATA", b"changed")]))
        result = compare(a, b)
        self.assertEqual(len(result["blocks"]), 2)
        self.assertEqual(result["unexpected_changes"], ["DATA[1]"])

    def test_explicit_metadata_allowlist(self):
        a = inspect_bytes(resource([("DATA", b"body"), ("RED2", b"old")]))
        b = inspect_bytes(resource([("DATA", b"body"), ("RED2", b"new")]))
        self.assertFalse(compare(a, b)["payload_allowlist_passed"])
        self.assertTrue(compare(a, b, ["RED2"])["payload_allowlist_passed"])

    def test_added_and_removed(self):
        a = inspect_bytes(resource([("DATA", b"body")]))
        b = inspect_bytes(resource([("PHYS", b"physics")]))
        result = compare(a, b)
        self.assertEqual([r["status"] for r in result["blocks"]], ["removed", "added"])

    def test_unsupported_header(self):
        raw = bytearray(resource([]))
        struct.pack_into("<H", raw, 4, 99)
        with self.assertRaises(ResourceError):
            inspect_bytes(raw)

    def test_truncated_header(self):
        with self.assertRaises(ResourceError):
            inspect_bytes(b"short")

    def test_bad_directory(self):
        raw = bytearray(resource([]))
        struct.pack_into("<I", raw, 12, 90000)
        with self.assertRaises(ResourceError):
            inspect_bytes(raw)

    def test_out_of_bounds_payload(self):
        raw = bytearray(resource([("DATA", b"x")]))
        struct.pack_into("<I", raw, 24, 9999)
        with self.assertRaises(ResourceError):
            inspect_bytes(raw)

    def test_overlapping_payloads(self):
        raw = bytearray(resource([("DATA", b"aaa"), ("PHYS", b"bbb")]))
        struct.pack_into("<I", raw, 32, 8)
        with self.assertRaises(ResourceError):
            inspect_bytes(raw)

    def test_unparsed_trailing_change_is_not_ignored(self):
        raw = resource([("DATA", b"body")])
        a, b = inspect_bytes(raw + b"a"), inspect_bytes(raw + b"b")
        self.assertEqual(compare(a, b)["unexpected_changes"], ["unparsed_trailing_data"])

    def test_resource_version_change_is_not_ignored(self):
        raw = resource([("DATA", b"body")])
        changed = bytearray(raw)
        struct.pack_into('<H', changed, 6, 2)
        result = compare(inspect_bytes(raw), inspect_bytes(changed), ['DATA'])
        self.assertEqual(result['unexpected_changes'], ['resource_version'])

    def test_allowlist_covers_added_removed_and_every_occurrence(self):
        a = inspect_bytes(resource([('DATA', b'a'), ('DATA', b'b')]))
        b = inspect_bytes(resource([('DATA', b'c')]))
        self.assertTrue(compare(a, b, ['DATA'])['payload_allowlist_passed'])

    def test_directory_reordering_reported(self):
        a = inspect_bytes(resource([('DATA', b'a'), ('PHYS', b'b')]))
        b = inspect_bytes(resource([('PHYS', b'b'), ('DATA', b'a')]))
        result = compare(a, b)
        self.assertFalse(result['block_directory_sequence_identical'])
        self.assertFalse(result['file_identical'])
        self.assertTrue(result['payload_allowlist_passed'])


class CliTests(unittest.TestCase):
    def run_cli(self, old, new, flags=(), missing=False):
        with tempfile.TemporaryDirectory(prefix='resource-block-test-') as temp:
            left, right = Path(temp) / 'baseline.bin', Path(temp) / 'candidate.bin'
            if not missing:
                left.write_bytes(old)
            right.write_bytes(new)
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main([str(left), str(right), *flags])
            return code, out.getvalue(), err.getvalue()

    def test_report_mode_differences_exit_zero(self):
        code, out, err = self.run_cli(resource([('DATA', b'a')]), resource([('DATA', b'b')]))
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(out)['payload_allowlist_passed'])
        self.assertEqual(err, '')

    def test_enforced_difference_exit_one(self):
        code, out, err = self.run_cli(resource([('DATA', b'a')]), resource([('DATA', b'b')]), ['--enforce'])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)['unexpected_changes'], ['DATA[0]'])
        self.assertEqual(err, '')

    def test_repeated_allowlist_exit_zero(self):
        a = resource([('DATA', b'a'), ('PHYS', b'b')])
        b = resource([('DATA', b'c'), ('PHYS', b'd')])
        code, out, err = self.run_cli(a, b, ['--allow-changed', 'DATA', '--allow-changed', 'PHYS', '--enforce'])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)['payload_allowlist_passed'])
        self.assertEqual(err, '')

    def test_missing_file_json_error_exit_two(self):
        code, out, err = self.run_cli(b'', resource([]), missing=True)
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('error', json.loads(err))

    def test_invalid_header_json_error_exit_two(self):
        code, out, err = self.run_cli(b'short', resource([]))
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('error', json.loads(err))

    def test_invalid_tag_exit_two(self):
        code, out, err = self.run_cli(resource([]), resource([]), ['--allow-changed', '*'])
        self.assertEqual(code, 2)
        self.assertEqual(out, '')
        self.assertIn('error', json.loads(err))

    def test_identical_enforced_exit_zero(self):
        raw = resource([('DATA', b'ok')])
        code, out, err = self.run_cli(raw, raw, ['--enforce'])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)['file_identical'])
        self.assertEqual(err, '')


if __name__ == "__main__":
    unittest.main()
