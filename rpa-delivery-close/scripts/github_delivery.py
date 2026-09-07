"""Read-only github.com evidence. Never create reviews, comments or checks."""
import json
import re
import subprocess


class EvidenceError(ValueError):
    pass


def github_url(value, kind):
    match = re.fullmatch(r'https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/'
                         + kind + r'/([1-9][0-9]*)', str(value))
    if not match:
        raise EvidenceError(f'Expected a canonical github.com {kind} URL')
    return match.group(1), int(match.group(2))


def api(endpoint, *, pages=False):
    command = ['gh', 'api', '--hostname', 'github.com', '--method', 'GET',
               '-H', 'Accept: application/vnd.github+json',
               '-H', 'X-GitHub-Api-Version: 2022-11-28', endpoint]
    if pages:
        command += ['--paginate', '--slurp']
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding='utf-8', timeout=45)
        if result.returncode:
            # Do not echo remote bodies, auth details or CLI diagnostics into evidence.
            raise EvidenceError('GitHub read failed: check authentication, permissions and resource availability')
        return json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise EvidenceError('GitHub evidence is unavailable; cannot assume a pass') from exc


class GitHub:
    def issue(self, url):
        repo, number = github_url(url, 'issues')
        item = api(f'repos/{repo}/issues/{number}')
        if item.get('pull_request') or item.get('html_url', '').lower() != url.lower():
            raise EvidenceError('Issue identity mismatch')
        return {'url': item['html_url'], 'state': item['state'], 'number': number,
                'updated_at': item['updated_at'], 'author': item['user']['login']}

    def pull(self, url):
        repo, number = github_url(url, 'pull')
        item = api(f'repos/{repo}/pulls/{number}')
        if item.get('html_url', '').lower() != url.lower():
            raise EvidenceError('PR identity mismatch')
        reviews = [r for page in api(f'repos/{repo}/pulls/{number}/reviews?per_page=100', pages=True)
                   for r in page]
        return {'url': url, 'head': item['head']['sha'], 'merge': item.get('merge_commit_sha'),
                'merged': item['merged'], 'state': item['state'], 'draft': item.get('draft', False),
                'created_at': item['created_at'], 'author': item['user']['login'], 'reviews': reviews}

    def checks(self, repo, commit):
        if not re.fullmatch(r'[0-9a-f]{40}', commit):
            raise EvidenceError('Invalid check commit')
        return [r for page in api(f'repos/{repo}/commits/{commit}/check-runs?per_page=100&filter=latest', pages=True)
                for r in page['check_runs']]

    def comment_record(self, url, repo, issue_number, pull_number):
        match = re.fullmatch(r'https://github\.com/' + re.escape(repo)
                             + r'/(issues|pull)/([1-9][0-9]*)#issuecomment-([1-9][0-9]*)', str(url))
        if not match:
            raise EvidenceError('Only linked Issue/PR conversation comments are supported as recorded evidence')
        number = int(match.group(2))
        if number != (issue_number if match.group(1) == 'issues' else pull_number):
            raise EvidenceError('Comment belongs to a different delivery')
        item = api(f'repos/{repo}/issues/comments/{match.group(3)}')
        if item.get('html_url', '').lower() != url.lower():
            raise EvidenceError('Comment identity mismatch')
        # Machine-readable supplement to normal prose, not a replacement for discussion.
        blocks = re.findall(r'```rpa-evidence\s*\n(.*?)\n```', item.get('body', ''), re.S)
        if len(blocks) != 1:
            raise EvidenceError('Comment needs exactly one rpa-evidence record; prose alone is historical evidence')
        try:
            record = json.loads(blocks[0])
        except ValueError as exc:
            raise EvidenceError('Invalid comment evidence record') from exc
        return record, {'kind': 'github_comment', 'url': url, 'author': item['user']['login'],
                        'updated_at': item['updated_at'], 'identity_limit': 'account identity, not proof of human authorship'}
