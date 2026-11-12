"""Exercise the hand-maintained formula workflows' inline release checks."""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parent.parent


def workflow(name):
    text = (ROOT / '.github' / 'workflows' / f'{name}.yml').read_text()
    job = re.search(r'(?ms)^  check-upstream:\n(.*?)(?=^  \S|\Z)', text).group(1)
    script = re.search(r'(?ms)^        run: \|\n((?:^          .*\n)+)', job).group(1)
    return job, textwrap.dedent(script)


class UpstreamCheckTests(unittest.TestCase):
    def run_check(self, name, latest, existing='', event='schedule', formula=None, fail_release=False):
        job, script = workflow(name)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'Formula').mkdir()
            (root / 'Formula' / f'{name}.rb').write_text(
                formula if formula is not None else (ROOT / 'Formula' / f'{name}.rb').read_text()
            )
            gh = root / 'gh'
            gh.write_text(textwrap.dedent('''\
                #!/usr/bin/env python3
                import json, os, sys
                args = sys.argv[1:]
                with open(os.environ['CALLS'], 'a') as f:
                    f.write(json.dumps(args) + '\\n')
                if args[:2] == ['release', 'view']:
                    if os.environ['FAIL_RELEASE'] == '1':
                        sys.exit(1)
                    print(os.environ['LATEST'])
                elif args[:2] == ['issue', 'list']:
                    print(os.environ['EXISTING'])
            '''))
            gh.chmod(0o755)
            calls = root / 'calls'
            env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}", CALLS=str(calls),
                       LATEST=latest, EXISTING=existing, FAIL_RELEASE=str(int(fail_release)),
                       GH_REPO='hivecommons/homebrew-hive', GITHUB_EVENT_NAME=event,
                       RUN_URL='https://example.com/run')
            result = subprocess.run(['bash', '-c', script], cwd=root, env=env, capture_output=True, text=True)
            return result, [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else []

    def test_drift_lifecycle(self):
        for name in ('crux', 'hotshot'):
            with self.subTest(name=name):
                formula = (ROOT / 'Formula' / f'{name}.rb').read_text()
                pinned = re.search(r'/(v\d+\.\d+\.\d+)(?:/|\.tar\.gz")', formula).group(1)
                job, _ = workflow(name)
                self.assertIn("if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'", job)
                for existing, action in [('', 'create'), ('42', 'comment')]:
                    result, calls = self.run_check(name, 'v9.0.0', existing)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(calls[0][:4], ['release', 'view', '--repo', f'hivecommons/{name}'])
                    self.assertEqual(calls[-1][:2], ['issue', action])
                    body = calls[-1][calls[-1].index('--body') + 1]
                    for value in (pinned, 'v9.0.0', 'Formula/README.md', 'https://example.com/run'):
                        self.assertIn(value, body)
                    if not existing:
                        self.assertEqual(calls[-1][calls[-1].index('--title') + 1], f'{name} formula behind upstream')
                result, calls = self.run_check(name, pinned, '42')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls[-1][:3], ['issue', 'close', '42'])
                for existing, event in [('', 'schedule'), ('42', 'workflow_dispatch')]:
                    result, calls = self.run_check(name, pinned, existing, event)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual([c[:2] for c in calls], [['release', 'view'], ['issue', 'list']])

    def test_errors_do_not_mutate_issues(self):
        for name in ('crux', 'hotshot'):
            for options in ({'formula': 'url "unexpected"\n'}, {'fail_release': True}, {'latest': ''}):
                with self.subTest(name=name, options=options):
                    args = {'latest': 'v9.0.0', **options}
                    result, calls = self.run_check(name, **args)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(any(c[:2] in (['issue', 'create'], ['issue', 'comment'], ['issue', 'close']) for c in calls))


if __name__ == '__main__':
    unittest.main()
