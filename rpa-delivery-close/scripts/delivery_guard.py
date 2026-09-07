"""Current-delivery preflight. Historical records are readable, never upgraded silently."""
import hashlib
import json
from pathlib import Path
import re
from github_delivery import EvidenceError, GitHub, github_url
from delivery_version import delivery_version, is_record_path


def local_file(root, ref):
    if not isinstance(ref, str) or not ref or Path(ref).is_absolute():
        raise EvidenceError('Evidence file must be repository-relative')
    path = (root / ref).resolve()
    if not path.is_relative_to(root):
        raise EvidenceError(f'Evidence file missing or outside repository: {ref}')
    if not path.is_file():
        parts = Path(ref).parts
        if len(parts) >= 4 and parts[:2] == ('.trellis', 'tasks') and parts[2] != 'archive':
            candidates = [p for p in (root / '.trellis/tasks/archive').glob('*/' + parts[2] + '/' + '/'.join(parts[3:]))
                          if p.is_file() and p.resolve().is_relative_to(root)]
            if len(candidates) == 1:
                return candidates[0].resolve()
        raise EvidenceError(f'Evidence file missing or ambiguous: {ref}')
    return path


def record(root, ref, expected_kind, binding, provider, repo, issue_number, pull_number):
    if str(ref).startswith('https://'):
        value, source = provider.comment_record(ref, repo, issue_number, pull_number)
    else:
        path = local_file(root, ref)
        value = json.loads(path.read_text(encoding='utf-8'))
        source = {'kind': 'local_record', 'path': str(ref), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value.get('schema_version') != 1:
        raise EvidenceError('Evidence record needs schema_version 1')
    for key, expected in {**binding, 'kind': expected_kind, 'result': 'passed'}.items():
        if value.get(key) != expected:
            raise EvidenceError(f'Evidence {key} does not match this delivery')
    if value.get('actor_kind') not in {'human', 'agent'} or not isinstance(value.get('actor'), str) or not value['actor'].strip():
        raise EvidenceError('Record must identify declared actor and human/agent provenance')
    if not str(value.get('statement', '')).strip():
        raise EvidenceError('Missing review/check/acceptance statement')
    artifact = value.get('artifact')
    if not isinstance(artifact, dict):
        raise EvidenceError('Record must reference the underlying local report/transcript')
    path = local_file(root, artifact.get('path'))
    raw = path.read_bytes()
    if not raw.strip() or hashlib.sha256(raw).hexdigest() != artifact.get('sha256'):
        raise EvidenceError('Underlying artifact missing, empty or changed')
    if expected_kind == 'local_check' and (
        value.get('exit_code') != 0 or isinstance(value.get('exit_code'), bool)
        or not isinstance(value.get('command'), list) or not value['command']
        or any(not isinstance(arg, str) for arg in value['command'])
    ):
        raise EvidenceError('Local check needs an actual command and zero exit code')
    return {**source, 'evidence_kind': expected_kind, 'actor_kind': value['actor_kind'],
            'actor': value['actor'], 'artifact': artifact,
            'assurance': 'source-linked attestation; not independent execution or identity verification'}


def check(c, root, task_input=None, stage='archive', *, user_accepted=False, provider=None):
    root = Path(root).resolve()
    provider = provider or GitHub()
    missing, facts = [], {}
    result = {'ok': False, 'ready': False, 'stage': stage, 'missing': missing, 'facts': facts,
              'historical_acceptance_changed': False}
    if stage not in {'G3', 'G4', 'G5', 'archive'}:
        missing.append('stage'); return result
    try:
        c.transaction.require_settled(root)
        task_file, task = c.match_task(root, task_input)
        task_snapshot = task_file.read_bytes()
        meta = task.get('meta') or {}
        archive = meta.get('archive_evidence') or {}
        requirements = meta.get('delivery_requirements') or {}
        contract = meta.get('delivery_contract')
        if not isinstance(contract, dict) or type(contract.get('schema_version')) is not int or contract.get('schema_version') != 1:
            missing.append('delivery_contract: explicit source policy and scope required; legacy record is not current clearance')
            return result
        if contract.get('confirmed') is not True or not isinstance(contract.get('scope'), str) or not contract['scope'].strip():
            raise EvidenceError('delivery_contract must have explicitly confirmed scope')
        if contract.get('review_source') not in {'github_review', 'recorded_review'}:
            raise EvidenceError('Select github_review or recorded_review explicitly')
        if contract.get('check_source') not in {'github_checks', 'local_checks'}:
            raise EvidenceError('Select github_checks or local_checks explicitly')
        names = contract.get('required_checks')
        if not isinstance(names, list) or not names or any(not isinstance(n, str) or not n.strip() for n in names) or len(set(names)) != len(names):
            raise EvidenceError('Explicit nonempty unique required_checks names are required')
        for key in ('require_pr', 'require_runner', 'require_user_acceptance'):
            if not isinstance(requirements.get(key), bool):
                missing.append('delivery_requirements.' + key)
        if missing:
            return result
        project = c.read_project_gate(root)
        if task.get('status') not in {'planning', 'in_progress'} or c.is_archive_path(task_file, root / '.trellis/tasks'):
            missing.append('task_not_active: archived acceptance remains historical')
        if meta.get('delivery_state') in {'blocked', 'paused', 'cancelled'}:
            missing.append('delivery_state')
        if len(c.active_tasks(root)) > 1:
            missing.append('multiple_active_tasks')
        config = root / '.trellis/config.yaml'
        if not config.is_file() or not re.search(r'(?m)^\s*session_auto_commit\s*:\s*false\s*(?:#.*)?$', config.read_text(encoding='utf-8')):
            missing.append('session_auto_commit_false')
        route_check = c.check_delivery_route(root, str(task_file))
        route = route_check.get('delivery_route')
        if stage == 'archive' and route:
            if set(route['required_reviews']) - set(route['completed_reviews']):
                missing.append('delivery_route_incomplete')
        commit = archive.get('commit') or task.get('commit')
        if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit):
            raise EvidenceError('Delivery commit must be an exact 40-character SHA')
        version = delivery_version(root, commit)
        facts['version'] = version
        if not all(version.get(k) for k in ('ok', 'delivery_tree_clean', 'baseline_compatible')):
            missing.append('delivery_version')
        issue_url = contract.get('issue_url')
        repo, issue_number = github_url(issue_url, 'issues')
        code, remote = c.run_git(root, ['remote', 'get-url', 'origin'])
        allowed = {f'https://github.com/{repo}', f'https://github.com/{repo}.git', f'git@github.com:{repo}.git'}
        if code or remote.strip().lower() not in {v.lower() for v in allowed}:
            raise EvidenceError('Issue repository must match the local origin')
        facts['issue'] = provider.issue(issue_url)
        facts['task_id'] = c.task_id(task_file, task)
        facts['scope'] = contract['scope']
        binding = {'task_id': facts['task_id'], 'commit': commit, 'issue_url': issue_url, 'scope': contract['scope']}
        pr, pull_number = None, None
        if requirements['require_pr']:
            url = archive.get('pr_url') or task.get('pr_url')
            pr_repo, pull_number = github_url(url, 'pull')
            if pr_repo.lower() != repo.lower():
                raise EvidenceError('PR and Issue belong to different repositories')
            pr = provider.pull(url)
            facts['pr'] = {k: v for k, v in pr.items() if k != 'reviews'}
            if pr['draft'] or (pr['state'] != 'open' and not pr['merged']):
                missing.append('pr_not_deliverable')
            # A merge/squash is eligible only with local evidence and unchanged delivery content.
            if commit not in {pr['head'], pr['merge'] if pr['merged'] else None}:
                missing.append('pr_commit_mismatch')
            if commit != pr['head']:
                code, changes = c.run_git(root, ['diff', '--name-only', '--no-renames', pr['head'], commit])
                if code or any(not is_record_path(p) for p in changes.splitlines()):
                    missing.append('merge_requires_new_review')
            latest = {}
            for review in pr['reviews']:
                if review.get('state') in {'APPROVED', 'CHANGES_REQUESTED', 'DISMISSED'}:
                    latest[review['user']['login']] = review
            if any(r['state'] == 'CHANGES_REQUESTED' for r in latest.values()):
                missing.append('github_changes_requested')
            if contract['review_source'] == 'github_review':
                approved = [r for r in latest.values() if r['state'] == 'APPROVED'
                            and r.get('commit_id') == pr['head'] and r['user']['login'] != pr['author']]
                facts['review'] = [{'kind': 'github_review', 'url': r['html_url'], 'author': r['user']['login'],
                                    'commit': r['commit_id']} for r in approved]
                if not approved:
                    missing.append('github_review')
        elif contract['review_source'] == 'github_review':
            missing.append('github_review_requires_pr')
        if contract['review_source'] == 'recorded_review':
            facts['review'] = record(root, archive.get('review_ref'), 'review', binding, provider, repo, issue_number, pull_number)
        if contract['check_source'] == 'github_checks':
            check_commit = pr['head'] if pr else commit
            checks = provider.checks(repo, check_commit)
            facts['checks'] = []
            for name in names:
                matches = [r for r in checks if r.get('name') == name and r.get('head_sha') == check_commit]
                # All apps publishing the same required name must pass; no cherry-picked duplicate.
                if not matches or any(r.get('status') != 'completed' or r.get('conclusion') != 'success' for r in matches):
                    missing.append('github_check:' + name)
                facts['checks'].extend({'kind': 'github_check', 'name': name, 'url': r.get('html_url'),
                                        'conclusion': r.get('conclusion'), 'commit': check_commit} for r in matches)
        else:
            refs = archive.get('check_refs') or {}
            facts['checks'] = [record(root, refs.get(name), 'local_check', {**binding, 'name': name},
                                     provider, repo, issue_number, pull_number) for name in names]
        if stage in {'G4', 'G5', 'archive'} and requirements['require_runner']:
            refs = archive.get('runner_refs')
            runners = []
            if not isinstance(refs, list) or not refs:
                missing.append('runner_summary')
            else:
                for ref in refs:
                    path = local_file(root, ref)
                    if not c.is_evidence_summary_path(path):
                        missing.append('runner_legacy_unbound'); continue
                    validation = c.validate_evidence_summary(root, path)
                    runners.append(validation)
                    if not validation['delivery_ready']:
                        missing.append('runner_not_delivery_ready')
                    summary = c.read_json(path)
                    input_ref = (archive.get('runner_inputs') or {}).get(ref)
                    input_path = local_file(root, input_ref)
                    if hashlib.sha256(input_path.read_bytes()).hexdigest() != summary.get('artifacts', {}).get('input', {}).get('sha256'):
                        missing.append('runner_input_binding')
                if not runners:
                    missing.append('runner_summary')
            facts['runner_checks'] = runners
        if stage in {'G5', 'archive'}:
            if requirements['require_user_acceptance']:
                if user_accepted:
                    facts['acceptance'] = {'kind': 'explicit_caller_confirmation', 'commit': commit,
                                           'scope': contract['scope'], 'not_independently_authenticated': True}
                else:
                    facts['acceptance'] = record(root, archive.get('acceptance_ref'), 'user_acceptance', binding,
                                                provider, repo, issue_number, pull_number)
                    if facts['acceptance']['actor_kind'] != 'human':
                        missing.append('user_acceptance_actor')
            for field in ('acceptance_criteria', 'technical_checks'):
                items = archive.get(field)
                if not isinstance(items, list) or not items:
                    missing.append(field); continue
                for item in items:
                    if not isinstance(item, dict) or item.get('result') not in {'passed', 'accepted', 'met', 'complete', 'completed'} or not item.get('evidence_refs'):
                        missing.append(field)
                        continue
                    refs = item['evidence_refs']
                    if not isinstance(refs, list):
                        missing.append(field + '.evidence_refs'); continue
                    for ref in refs:
                        if ref in {issue_url, pr['url'] if pr else None, 'commit:' + commit}:
                            continue
                        local_file(root, ref)
            if not str(archive.get('final_summary', '')).strip():
                missing.append('final_summary')
        if stage == 'archive' and (project['current_gate'] != 'G5' or project['status'] != 'operational'):
            missing.append('project_not_operational')
        if pr:
            latest_pr = provider.pull(pr['url'])
            if any(latest_pr.get(k) != pr.get(k) for k in ('head', 'merge', 'merged', 'state', 'draft', 'reviews')):
                missing.append('github_changed_during_check')
        if delivery_version(root, commit) != version:
            missing.append('local_version_changed_during_check')
        if task_file.read_bytes() != task_snapshot:
            missing.append('task_changed_during_check')
        c.transaction.require_settled(root)
    except (EvidenceError, c.CollabError, c.transaction.TransactionError, OSError,
            ValueError, KeyError, TypeError, AttributeError) as exc:
        missing.append(str(exc))
    result['ok'] = result['ready'] = not missing
    return result
