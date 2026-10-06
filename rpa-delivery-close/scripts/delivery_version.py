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


def committed_paths(repo, baseline, head):
    """Inspect new commits without re-counting accepted code at a merge."""
    changed = set()
    contains_baseline = {baseline: True}
    for line in git(repo, 'rev-list', '--parents', f'{baseline}..{head}').splitlines():
        commit, *parents = line.split()
        if len(parents) > 1:
            for parent in parents:
                if parent not in contains_baseline:
                    try:
                        git(repo, 'merge-base', '--is-ancestor', baseline, parent)
                        contains_baseline[parent] = True
                    except subprocess.CalledProcessError as exc:
                        if exc.returncode != 1:
                            raise
                        contains_baseline[parent] = False
            # An older main parent lacks code already accepted on the feature
            # branch. Compare to accepted-lineage parents instead. Side-branch
            # commits are still visited individually, including reverted edits.
            parents = [p for p in parents if contains_baseline[p]] or parents
        if not parents:
            changed |= paths(git(repo, 'diff-tree', '--root', '--no-commit-id',
                                 '-r', '--name-only', '--no-renames', '-z', commit))
        for parent in parents:
            changed |= paths(git(repo, 'diff', '--name-only', '--no-renames', '-z', parent, commit))
    return changed


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
            git(repo, 'merge-base', '--is-ancestor', baseline, result['head'])
            committed = committed_paths(repo, baseline, result['head'])
        result['committed_paths'] = sorted(committed)
        result['baseline_compatible'] = not any(not is_record_path(p) for p in committed)
        result['delivery_paths'] = sorted(p for p in working | committed if not is_record_path(p))
        result['ok'] = True
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        result['error'] = str(exc)
    return result
