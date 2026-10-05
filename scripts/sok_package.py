"""Verify the curated SoK data archives before reading or materializing them."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def safe_path(name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or str(p) != name or not p.parts:
        raise ValueError('Unsafe archive path: ' + name)
    if any(x in {'.git', '.ssh'} or x.startswith(('.env', 'kubeconfig')) for x in p.parts):
        raise ValueError('Forbidden archive path: ' + name)
    return p


def inspect_archive(path, spec, destination=None, patterns=None):
    """Validate every member; optionally write it to a fresh isolated directory.

    No links, special files, traversal, nested archives, unlisted members or
    unbounded expansion are accepted. Never use tar.extractall on these inputs.
    """
    if path.stat().st_size != spec['bytes'] or sha256(path) != spec['sha256']:
        raise ValueError('Archive hash/size mismatch: ' + str(path))
    if spec['bytes'] > 90_000_000 or spec['expanded_bytes'] > 600_000_000:
        raise ValueError('Archive exceeds reviewed size: ' + str(path))
    count = expanded = 0
    with tarfile.open(path, 'r|gz') as tar:
        members = iter(tar)
        first = next(members, None)
        if first is None or first.name != 'DATA-MANIFEST.json' or not first.isfile() or first.size > 8_000_000:
            raise ValueError('Missing bounded archive manifest')
        raw = tar.extractfile(first).read()
        if hashlib.sha256(raw).hexdigest() != spec['manifest_sha256']:
            raise ValueError('Archive manifest hash mismatch')
        rows = json.loads(raw)['files']
        expected = {r['path']: r for r in rows}
        if len(expected) != len(rows) or len(rows) != spec['files']:
            raise ValueError('Duplicate or missing manifest entries')
        for name in expected:
            safe_path(name)
        seen = set()
        for member in members:
            name = member.name
            rel = safe_path(name)
            if name in seen or name not in expected or not member.isfile() or member.size > 100_000_000:
                raise ValueError('Unlisted, duplicate, non-file or oversized member: ' + name)
            row = expected[name]
            if member.size != row['bytes']:
                raise ValueError('Member size mismatch: ' + name)
            raw = tar.extractfile(member).read()
            if hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('Member hash mismatch: ' + name)
            if rel.suffix in {'.pdf', '.png'}:
                magic = b'%PDF-' if rel.suffix == '.pdf' else b'\x89PNG\r\n\x1a\n'
                if not raw.startswith(magic):
                    raise ValueError('Binary signature mismatch: ' + name)
            else:
                text = raw.decode('utf-8')
                for label, pattern in (patterns or {}).items():
                    if re.search(pattern, text):
                        raise ValueError('Credential pattern ' + label + ' in ' + name)
            if destination is not None:
                target = destination.joinpath(*rel.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                # Archives may share no target paths, including across packs.
                with target.open('xb') as handle:
                    handle.write(raw)
            seen.add(name)
            count += 1
            expanded += len(raw)
        if seen != set(expected) or expanded != spec['expanded_bytes']:
            raise ValueError('Incomplete archive: ' + str(path))
    return {'files': count, 'expanded_bytes': expanded}
