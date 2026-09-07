"""Recoverable local Gate writes; no Task lifecycle or external side effects."""
from contextlib import contextmanager
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import tempfile


class TransactionError(RuntimeError):
    pass


def pending_path(root):
    return Path(root) / '.project-gates' / 'pending-operation.json'


def text_at(path):
    return path.read_bytes().decode('utf-8') if path.exists() else None


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(text.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def project_lock(root):
    # OS-owned lock is released even after a killed process. It is outside Git.
    key = hashlib.sha256(str(Path(root).resolve()).casefold().encode()).hexdigest()
    path = Path(tempfile.gettempdir()) / ('rpa-gate-' + key + '.lock')
    with path.open('a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise TransactionError('Another Gate writer is active; retry after it exits') from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def require_settled(root):
    if pending_path(root).exists():
        raise TransactionError('Unfinished Gate operation; inspect status and use operation-recover first')


def guarded(function):
    @wraps(function)
    def call(args):
        with project_lock(args.project_root):
            require_settled(args.project_root)
            return function(args)
    return call


def inspect(root):
    path = pending_path(root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return {'state': 'pending', 'event_id': data.get('event_id'), 'path': str(path)}
    except (OSError, ValueError, AttributeError):
        return {'state': 'invalid', 'path': str(path)}


def digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def prepare(root, event_id, writes):
    require_settled(root)
    root = Path(root).resolve()
    entries = [{'path': path.relative_to(root).as_posix(), 'before': text_at(path), 'after': text}
               for path, text in writes.items()]
    data = {'schema_version': 1, 'event_id': event_id, 'writes': entries}
    data['sha256'] = digest(data)
    atomic_text(pending_path(root), json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def apply_pending(root, json_writer, *, dry_run=False):
    root = Path(root).resolve()
    journal = pending_path(root)
    if not journal.exists():
        return {'ok': True, 'status': 'nothing_pending', 'dry_run': dry_run}
    try:
        data = json.loads(journal.read_text(encoding='utf-8'))
        checksum = data.pop('sha256')
        if data.get('schema_version') != 1 or checksum != digest(data):
            raise ValueError('journal integrity mismatch')
        entries = data['writes']
        if not isinstance(entries, list) or not 2 <= len(entries) <= 3:
            raise ValueError('invalid write set')
        paths = []
        for entry in entries:
            relative = entry['path']
            path = (root / relative).resolve()
            parts = Path(relative).parts
            allowed = relative in {'.project-gates/project.json', '.project-gates/gate-history.md'} or (
                len(parts) == 4 and parts[:2] == ('.trellis', 'tasks') and parts[2] != 'archive' and parts[-1] == 'task.json')
            if not allowed or not path.is_relative_to(root) or path in paths:
                raise ValueError('unsafe or duplicate transaction path')
            if entry['before'] is not None and not isinstance(entry['before'], str):
                raise ValueError('invalid before image')
            if not isinstance(entry['after'], str):
                raise ValueError('invalid after image')
            paths.append(path)
        if {'.project-gates/project.json', '.project-gates/gate-history.md'} - {e['path'] for e in entries}:
            raise ValueError('missing authority writes')
        # Check all conflicts before applying any remaining write.
        for path, entry in zip(paths, entries):
            if text_at(path) not in (entry['before'], entry['after']):
                raise TransactionError(f'Concurrent change in {entry["path"]}; preserve files and resolve conflict before recovery')
        if dry_run:
            return {'ok': True, 'status': 'recoverable', 'event_id': data['event_id'], 'dry_run': True}
        for path, entry in zip(paths, entries):
            current = text_at(path)
            if current == entry['after']:
                continue
            if current != entry['before']:
                raise TransactionError(f'Concurrent change in {entry["path"]}')
            if path.suffix == '.json':
                json_writer(path, json.loads(entry['after']))
            else:
                atomic_text(path, entry['after'])
        if any(text_at(path) != entry['after'] for path, entry in zip(paths, entries)):
            raise TransactionError('Transaction read-back mismatch')
        journal.unlink()
        return {'ok': True, 'status': 'recovered', 'event_id': data['event_id'], 'dry_run': False}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise TransactionError(f'Cannot complete Gate operation; journal preserved: {exc}') from exc
