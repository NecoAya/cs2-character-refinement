#!/usr/bin/env python3
"""Read-only Source 2 header-v12 block-payload comparison; not semantic validation."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys


class ResourceError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inspect_bytes(data):
    if len(data) < 16:
        raise ResourceError("Truncated resource header (need 16 bytes)")
    declared, header, version, relative, count = struct.unpack_from("<IHHII", data)
    if header != 12:
        raise ResourceError(f"Unsupported header version {header}; only v12 was tested")
    if not 16 <= declared <= len(data):
        raise ResourceError("Declared resource size is outside the file")
    table = 8 + relative
    if table < 16 or count > 100000 or table + count * 12 > declared:
        raise ResourceError("Invalid or truncated block directory")
    blocks, seen, spans = [], {}, []
    for index in range(count):
        at = table + index * 12
        tag_bytes, offset, size = struct.unpack_from("<4sII", data, at)
        try:
            tag = tag_bytes.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ResourceError("Non-ASCII block tag") from exc
        if len(tag) != 4 or not all(c.isupper() or c.isdigit() or c == "_" for c in tag):
            raise ResourceError(f"Unsupported block tag {tag!r}")
        start = at + 4 + offset
        if start < 0 or start + size > declared:
            raise ResourceError(f"Block {tag} extends outside declared resource")
        if size:
            if start < table + count * 12:
                raise ResourceError(f"Block {tag} overlaps header/directory")
            spans.append((start, start + size))
        occurrence = seen.get(tag, 0)
        seen[tag] = occurrence + 1
        blocks.append({"id": f"{tag}[{occurrence}]", "tag": tag,
                       "ordinal": index, "offset": start, "size": size,
                       "sha256": digest(data[start:start + size])})
    spans.sort()
    if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
        raise ResourceError("Overlapping block payloads; layout not supported")
    return {"file_bytes": len(data), "declared_bytes": declared,
            "header_version": header, "resource_version": version,
            "sha256": digest(data), "trailing_bytes": len(data) - declared,
            "trailing_sha256": digest(data[declared:]), "blocks": blocks}


def compare(left, right, allowed=()):
    a = {b["id"]: b for b in left["blocks"]}
    b = {b["id"]: b for b in right["blocks"]}
    rows = []
    for key in sorted(a.keys() | b.keys()):
        old, new = a.get(key), b.get(key)
        status = ("added" if old is None else "removed" if new is None else
                  "same" if (old["size"], old["sha256"]) ==
                  (new["size"], new["sha256"]) else "changed")
        rows.append({"id": key, "tag": (new or old)["tag"], "status": status,
                     "before_bytes": old["size"] if old else None,
                     "after_bytes": new["size"] if new else None})
    changed = [r for r in rows if r["status"] != "same"]
    unexpected = [r["id"] for r in changed if r["tag"] not in allowed]
    if left["resource_version"] != right["resource_version"]:
        unexpected.append("resource_version")
    if left["trailing_sha256"] != right["trailing_sha256"]:
        unexpected.append("unparsed_trailing_data")
    return {"file_identical": left["sha256"] == right["sha256"],
            "block_directory_sequence_identical": list(a) == list(b),
            "blocks": rows, "allowed_changed_tags": sorted(set(allowed)),
            "unexpected_changes": unexpected,
            "payload_allowlist_passed": not unexpected,
            "limitations": "Payload hashes only, not physics/geometry/appearance validation. "
            "Same-name blocks match by occurrence; relocation/padding are not semantic checks."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--allow-changed", action="append", default=[], metavar="TAG")
    parser.add_argument("--enforce", action="store_true",
                        help="Exit 1 for changed payloads outside the explicit allowlist")
    args = parser.parse_args(argv)
    try:
        for tag in args.allow_changed:
            if len(tag) != 4 or not all(c.isupper() or c.isdigit() or c == "_" for c in tag):
                raise ResourceError(f"Invalid allowlist tag {tag!r}")
        before = inspect_bytes(args.baseline.read_bytes())
        after = inspect_bytes(args.candidate.read_bytes())
        result = compare(before, after, args.allow_changed)
        result.update(baseline=before, candidate=after)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 1 if args.enforce and not result["payload_allowlist_passed"] else 0
    except (OSError, ResourceError, struct.error) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
