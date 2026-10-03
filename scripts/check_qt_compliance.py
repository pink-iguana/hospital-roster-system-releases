"""Three offline checks for selection, correspondence and truthful failure reports."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from verify_qt_compliance import APP_PATTERN, Verification, check_source_reference, newest


class ComplianceChecks(unittest.TestCase):
    def test_latest_application_includes_prereleases_and_excludes_sources_drafts(self):
        releases = [{'tag_name': tag, 'draft': draft, 'published_at': date, 'id': i}
                    for i, (tag, draft, date) in enumerate([
                        ('v1.0.0', False, '2026-01-01'),
                        ('v1.1.0-beta', False, '2026-01-02'),
                        ('qt-6.7.3-source-3', False, '2026-01-03'),
                        ('v1.2.0', True, '2026-01-04')])]
        self.assertEqual(newest(releases, APP_PATTERN)['tag_name'], 'v1.1.0-beta')
        self.assertEqual(newest(releases, APP_PATTERN, 'v1.0.0')['tag_name'], 'v1.0.0')
        with self.assertRaises(RuntimeError):
            newest(releases, APP_PATTERN, 'v1.2.0')

    def test_source_url_and_digest_must_both_match(self):
        notice = 'Download URL: https://example.test/source\nSHA-256: ' + 'a' * 64
        check_source_reference(notice, 'https://example.test/source', 'a' * 64)
        for url, sha in [('https://example.test/other', 'a' * 64),
                         ('https://example.test/source', 'b' * 64)]:
            with self.assertRaisesRegex(RuntimeError, 'does not match'):
                check_source_reference(notice, url, sha)

    def test_failed_preflight_does_not_claim_later_stages_passed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            selection = root / 'selection.json'
            selection.write_text(json.dumps({'app': {'tag_name': 'v1.0.0'},
                                              'source': {'tag_name': 'qt-6.7.3-source-3'}}))
            verification = Verification('windows', selection, root)
            with patch.object(verification.native, 'preflight', side_effect=RuntimeError('No desktop')):
                with self.assertRaisesRegex(RuntimeError, 'No desktop'):
                    verification.verify()
            report = json.loads((root / 'evidence/results.json').read_text())
            self.assertEqual(report['status'], 'failed')
            self.assertEqual(report['stages']['desktop']['status'], 'failed')
            self.assertTrue(all(item['status'] == 'not_run' for name, item in report['stages'].items()
                                if name != 'desktop'))


if __name__ == '__main__':
    unittest.main()
