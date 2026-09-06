"""Git delivery identity; mirrored by the independent Controller distribution."""
import re
import subprocess


def is_record_path(path):
    """Only data records may change without requiring another runtime validation."""
    if path in {'.project-gates/project.json', '.project-gates/gate-history.md'}:
        return True
    if re.fullmatch(r'evidence/runs/[A-Za-z0-9_-][A-Za-z0-9._-]*\.summary\.json', path):
        return True
    parts = path.split('/')
    return (len(parts) >= 3 and parts[:2] in [['.trellis', 'tasks'], ['.trellis', 'workspace']]
            and not any(part in {'', '.', '..'} for part in parts)
            and path.endswith(('.md', '.json', '.jsonl')))


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], check=True,
                          capture_output=True, text=True, encoding='utf-8', timeout=10).stdout


def paths(output):
    return {path for path in output.split('\0') if path}


def delivery_version(repo, baseline=None):
    """Fail closed on Git errors, divergence, staged edits, renames and unknown files."""
    result = {'ok': False, 'head': '', 'working_tree_clean': False,
              'delivery_tree_clean': False, 'baseline_compatible': False,
              'working_paths': [], 'committed_paths': [], 'delivery_paths': []}
    try:
        result['head'] = git(repo, 'rev-parse', 'HEAD').strip()
        working = paths(git(repo, 'diff', '--name-only', '--no-renames', '-z', 'HEAD'))
        # Include index edits even when working content happens to match HEAD.
        working |= paths(git(repo, 'diff', '--cached', '--name-only', '--no-renames', '-z'))
        working |= paths(git(repo, 'ls-files', '--others', '--exclude-standard', '-z'))
        result['working_paths'] = sorted(working)
        result['working_tree_clean'] = not working
        result['delivery_tree_clean'] = not any(not is_record_path(p) for p in working)
        committed = set()
        if baseline is not None:
            if not re.fullmatch(r'[0-9a-fA-F]{40}', baseline):
                raise ValueError('baseline must be an exact commit')
            git(repo, 'merge-base', '--is-ancestor', baseline, 'HEAD')
            # Inspect every intervening commit, not just the final net diff.
            for commit in git(repo, 'rev-list', f'{baseline}..HEAD').splitlines():
                committed |= paths(git(repo, 'diff-tree', '--root', '-m', '--no-commit-id',
                                       '-r', '--name-only', '--no-renames', '-z', commit))
        result['committed_paths'] = sorted(committed)
        result['baseline_compatible'] = not any(not is_record_path(p) for p in committed)
        result['delivery_paths'] = sorted(p for p in working | committed if not is_record_path(p))
        result['ok'] = True
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        result['error'] = str(exc)
    return result
