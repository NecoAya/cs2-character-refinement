"""Checks the limits of the project's basic privacy-pattern guard."""
import unittest

from validate_project import contains_sensitive_pattern


class PrivacyPatternTests(unittest.TestCase):
    def test_https_is_not_a_windows_drive(self):
        self.assertFalse(contains_sensitive_pattern('https://github.com/example/repo'))

    def test_windows_absolute_path(self):
        self.assertTrue(contains_sensitive_pattern('C' + ':/' + 'Users/example/private.txt'))
        self.assertTrue(contains_sensitive_pattern('D' + ':\\private\\asset.bin'))

    def test_unix_personal_paths(self):
        self.assertTrue(contains_sensitive_pattern('/' + 'home/example/asset'))
        self.assertTrue(contains_sensitive_pattern('/' + 'Users/example/asset'))

    def test_relative_paths_allowed(self):
        self.assertFalse(contains_sensitive_pattern('references/evidence-case.md'))

    def test_token_patterns(self):
        self.assertTrue(contains_sensitive_pattern('ghp_' + 'x' * 36))
        self.assertTrue(contains_sensitive_pattern('github_pat_' + 'x' * 40))

    def test_private_key_marker(self):
        self.assertTrue(contains_sensitive_pattern('-----BEGIN ' + 'RSA PRIVATE KEY-----'))


if __name__ == '__main__':
    unittest.main()
