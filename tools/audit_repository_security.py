"""Scan working sources and reachable Git text blobs; output locations, never values."""
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
GIT = ['git', '-c', 'safe.directory=' + ROOT.as_posix()]
TEXT = {'.py', '.js', '.html', '.css', '.sql', '.json', '.yml', '.yaml', '.md', '.txt', '.example'}
PATTERNS = {
    'private key material': re.compile(r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----'),
    'Firebase web API identifier (public client configuration; review API restrictions)': re.compile(r'AIza[0-9A-Za-z_-]{30,}'),
    'credential in connection URL': re.compile(r'(?:mysql|amqp|amqps)(?:\+\w+)?://[^\s:/]+:([^\s@]+)@'),
    'literal development password': re.compile(r'(?i)(?:\b(?:MYSQL_ROOT_PASSWORD|MYSQL_PASSWORD|RABBITMQ_DEFAULT_PASS)\s*:\s*[\"\x27]?([a-z0-9_!@-]{6,})|os\.getenv\([\"\x27]RABBITMQ_PASSWORD[\"\x27],\s*[\"\x27]([^\"\x27]+))'),
}


def scan(source, file, scope):
    findings = []
    for detector, pattern in PATTERNS.items():
        for match in pattern.finditer(source):
            value = next((group for group in match.groups() if group), match.group())
            if any(marker in value.lower() for marker in ('change', 'replace-with', 'example', 'placeholder', 'password_here', 'your_', '<', '${', '{env[', 'test-only', 'synthetic')):
                continue
            findings.append({'file': file, 'scope': scope, 'detector': detector,
                             'line': source.count('\n', 0, match.start()) + 1})
    return findings


def main():
    tracked = subprocess.check_output(GIT + ['ls-files'], cwd=ROOT, text=True).splitlines()
    candidates = set(tracked)
    candidates.update(subprocess.check_output(GIT + ['ls-files', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines())
    findings = []
    for name in sorted(candidates):
        path = ROOT / name
        if path.is_file() and path.suffix.lower() in TEXT and path.stat().st_size < 2_000_000:
            findings.extend(scan(path.read_text(encoding='utf-8', errors='replace'), name, 'working tree'))
    objects = subprocess.check_output(GIT + ['rev-list', '--objects', '--all'], cwd=ROOT, text=True).splitlines()
    blobs = {}
    for item in objects:
        oid, _, name = item.partition(' ')
        if name and (Path(name).suffix.lower() in TEXT or Path(name).name.startswith('.env')):
            blobs[oid] = name
    # Batch access avoids one Git process per blob. Binary/large blobs are skipped.
    result = subprocess.run(GIT + ['cat-file', '--batch'], input=('\n'.join(blobs) + '\n').encode(),
                            cwd=ROOT, capture_output=True, check=True)
    position = 0
    scanned = 0
    for oid, name in blobs.items():
        end = result.stdout.index(b'\n', position)
        header = result.stdout[position:end].split()
        size = int(header[-1])
        data = result.stdout[end+1:end+1+size]
        position = end+1+size+1
        if header[1] != b'blob' or size > 2_000_000 or b'\x00' in data:
            continue
        scanned += 1
        for finding in scan(data.decode('utf-8', errors='replace'), name, 'reachable Git history'):
            finding['blob'] = oid
            findings.append(finding)
    unique = {(item['file'], item['scope'], item['detector']): item for item in findings}
    report = {'method': 'Pattern scan of working text files and reachable Git text blobs. Heuristic, not a proof of secret absence. Matches are never printed.',
              'working_files_considered': len(candidates), 'historical_blobs_scanned': scanned,
              'tracked_private_env_files': [name for name in tracked if Path(name).name == '.env'],
              'findings': list(unique.values())}
    (ROOT / 'docs/testing/secret_scan.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
