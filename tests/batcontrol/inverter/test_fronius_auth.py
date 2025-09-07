"""Tests for Fronius inverter authentication functionality."""
import unittest
import hashlib
from packaging import version

from batcontrol.inverter.fronius import hash_utf8, get_api_config, FroniusApiConfig


class TestFroniusAuthentication(unittest.TestCase):
    """Test authentication algorithm selection based on firmware version."""

    def test_hash_utf8_md5_default(self):
        """Test that hash_utf8 defaults to MD5."""
        test_string = "test_string"
        result = hash_utf8(test_string)
        expected = hashlib.md5(test_string.encode('utf-8')).hexdigest()
        self.assertEqual(result, expected)

    def test_hash_utf8_md5_explicit(self):
        """Test hash_utf8 with explicit MD5 algorithm."""
        test_string = "test_string"
        result = hash_utf8(test_string, "MD5")
        expected = hashlib.md5(test_string.encode('utf-8')).hexdigest()
        self.assertEqual(result, expected)

    def test_hash_utf8_sha256(self):
        """Test hash_utf8 with SHA256 algorithm."""
        test_string = "test_string"
        result = hash_utf8(test_string, "SHA256")
        expected = hashlib.sha256(test_string.encode('utf-8')).hexdigest()
        self.assertEqual(result, expected)

    def test_hash_utf8_case_insensitive(self):
        """Test that algorithm parameter is case insensitive."""
        test_string = "test_string"
        result_upper = hash_utf8(test_string, "SHA256")
        result_lower = hash_utf8(test_string, "sha256")
        result_mixed = hash_utf8(test_string, "Sha256")
        self.assertEqual(result_upper, result_lower)
        self.assertEqual(result_upper, result_mixed)

    def test_api_config_version_before_1_38_6_1_uses_md5(self):
        """Test that firmware versions before 1.38.6-1 use MD5."""
        test_versions = ["1.35.0", "1.36.0", "1.37.0", "1.38.5"]
        for v in test_versions:
            with self.subTest(version=v):
                parsed_version = version.parse(v)
                config = get_api_config(parsed_version)
                self.assertEqual(config.auth_algorithm, "MD5")

    def test_api_config_version_1_38_6_1_and_later_uses_sha256(self):
        """Test that firmware version 1.38.6-1 and later use SHA256."""
        test_versions = ["1.38.6-1", "1.38.7", "1.39.0", "2.0.0"]
        for v in test_versions:
            with self.subTest(version=v):
                parsed_version = version.parse(v)
                config = get_api_config(parsed_version)
                self.assertEqual(config.auth_algorithm, "SHA256")

    def test_api_config_boundary_version(self):
        """Test the exact boundary version 1.38.6-1."""
        # Version just before the boundary should use MD5
        version_before = version.parse("1.38.5")
        config_before = get_api_config(version_before)
        self.assertEqual(config_before.auth_algorithm, "MD5")
        
        # The boundary version should use SHA256
        boundary_version = version.parse("1.38.6-1")
        config_boundary = get_api_config(boundary_version)
        self.assertEqual(config_boundary.auth_algorithm, "SHA256")

    def test_hash_utf8_with_bytes_input(self):
        """Test hash_utf8 with bytes input."""
        test_bytes = b"test_bytes"
        result_md5 = hash_utf8(test_bytes, "MD5")
        result_sha256 = hash_utf8(test_bytes, "SHA256")
        
        expected_md5 = hashlib.md5(test_bytes).hexdigest()
        expected_sha256 = hashlib.sha256(test_bytes).hexdigest()
        
        self.assertEqual(result_md5, expected_md5)
        self.assertEqual(result_sha256, expected_sha256)


if __name__ == '__main__':
    unittest.main()