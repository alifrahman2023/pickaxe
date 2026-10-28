"""Unbounded, fixture-sized experiment; never imported by the product CLI.

Whole helper outputs and blobs live in RAM. This is neither the accounted
production builder nor an eligibility gate nor a replay implementation.
"""
from collections import defaultdict


class CandidateModel:
    def __init__(self, git, *, coverage=None, cwd=None, chunk_size=7):
        self.git = git
        if chunk_size <= 0:
            raise ValueError('chunk size must be positive')
        rows = git('rev-list', '--all', '--parents').decode().splitlines()
        self.parents = {row.split()[0]: row.split()[1:] for row in rows}
        self.coverage = set(self.parents) if coverage is None else set(coverage)
        self.associations = defaultdict(set)
        self.always = set()
        for commit, parents in self.parents.items():
            if commit not in self.coverage:
                continue
            if len(parents) > 1:
                self.always.add(commit)
                continue
            raw = git('diff-tree', '--root', '-r', '--raw', '-z', '--no-commit-id',
                      '--no-abbrev', '--no-renames', '--no-ext-diff', '--no-textconv',
                      '--ignore-submodules=none', '--no-relative', commit, '--', cwd=cwd)
            fields = raw.split(b'\0')
            if fields.pop() != b'' or len(fields) % 2:
                raise ValueError('incomplete raw change enumeration')
            for header, path in zip(fields[::2], fields[1::2]):
                parts = header.split()
                if len(parts) != 5 or not header.startswith(b':') or not path:
                    raise ValueError('invalid raw change record')
                old_mode, new_mode, old, new, status = parts
                old_mode = old_mode[1:]
                if status not in (b'A', b'D', b'M', b'T'):
                    raise ValueError('unexpected paired/unknown change')
                if b'160000' in (old_mode, new_mode):
                    self.always.add(commit)
                for mode, oid in ((old_mode, old), (new_mode, new)):
                    if mode in (b'100644', b'100755', b'120000'):
                        self.associations[oid.decode()].add(commit)
                    elif mode not in (b'000000', b'160000'):
                        raise ValueError('unsupported raw mode')
        # One size-delimited batch for distinct blob IDs; not one Git per blob.
        ids = sorted(self.associations)
        batch = git('cat-file', '--batch', input=''.join(i + '\n' for i in ids).encode())
        self.postings = defaultdict(set)
        self.blobs = {}
        offset = 0
        for oid in ids:
            end = batch.index(b'\n', offset)
            header = batch[offset:end].split()
            if len(header) != 3 or header[:2] != [oid.encode(), b'blob']:
                raise ValueError('missing or invalid blob header')
            size = int(header[2])
            if size < 0:
                raise ValueError('negative blob size')
            offset = end + 1
            content = batch[offset:offset + size]
            if len(content) != size or batch[offset + size:offset + size + 1] != b'\n':
                raise ValueError('truncated blob framing')
            offset += size + 1
            self.blobs[oid] = content
            tail = b''
            for start in range(0, size, chunk_size):
                block = tail + content[start:start + chunk_size]
                for i in range(len(block) - 2):
                    self.postings[block[i:i + 3]].add(oid)
                tail = block[-2:]
        if offset != len(batch):
            raise ValueError('extra batch output')

    def query(self, needle):
        if len(needle) < 3:
            raise ValueError('short needles require whole-search Git fallback')
        current = self.git('rev-list', '--all').decode().splitlines()
        trigrams = {needle[i:i + 3] for i in range(len(needle) - 2)}
        blobs = set.intersection(*(set(self.postings[t]) for t in trigrams))
        associated = set().union(*(self.associations[b] for b in blobs))
        candidates = [c for c in current if c not in self.coverage
                      or c in self.always or c in associated]
        return dict(path='fixture-blob-filter', needle_hex=needle.hex(),
                    coverage=sorted(self.coverage), always_check=sorted(self.always),
                    matching_blobs=sorted(blobs), candidates=candidates, scope=current,
                    associations={b: sorted(cs) for b, cs in sorted(self.associations.items())})
