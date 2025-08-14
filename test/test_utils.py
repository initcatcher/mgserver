import unittest
import sys
import os

# Add the parent directory to the Python path so we can import utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import utils


class TestConvertUrlToPath(unittest.TestCase):
    """Test cases for convert_url_to_path function"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.source_url = "https://image.nearzoom.store/media/"
        self.target_path = "/home/catch/media/"
    
    def test_convert_valid_url(self):
        """Test converting a valid URL that starts with source_url"""
        url = "https://image.nearzoom.store/media/images/test.jpg"
        expected = "/home/catch/media/images/test.jpg"
        result = utils.convert_url_to_path(url)
        self.assertEqual(result, expected)
    
    def test_convert_url_with_subdirectories(self):
        """Test converting URL with nested subdirectories"""
        url = "https://image.nearzoom.store/media/uploads/2024/01/image.png"
        expected = "/home/catch/media/uploads/2024/01/image.png"
        result = utils.convert_url_to_path(url)
        self.assertEqual(result, expected)
    
    def test_convert_url_exact_match(self):
        """Test converting URL that exactly matches source_url"""
        url = "https://image.nearzoom.store/media/"
        expected = "/home/catch/media/"
        result = utils.convert_url_to_path(url)
        self.assertEqual(result, expected)
    
    def test_non_matching_url_unchanged(self):
        """Test that URLs not starting with source_url are returned unchanged"""
        url = "https://example.com/media/image.jpg"
        result = utils.convert_url_to_path(url)
        self.assertEqual(result, url)
    
    def test_http_url_unchanged(self):
        """Test that HTTP URLs (not HTTPS) are unchanged"""
        url = "http://image.nearzoom.store/media/test.jpg"
        result = utils.convert_url_to_path(url)
        self.assertEqual(result, url)
    
    def test_partial_match_unchanged(self):
        """Test that partial matches don't get converted"""
        url = "https://image.nearzoom.store/different-media/test.jpg"
        result = utils.convert_url_to_path(url)
        self.assertEqual(result, url)
    
    def test_empty_string(self):
        """Test handling of empty string"""
        url = ""
        result = utils.convert_url_to_path(url)
        self.assertEqual(result, "")
    
    def test_local_path_unchanged(self):
        """Test that local file paths are unchanged"""
        url = "/home/user/images/test.jpg"
        result = utils.convert_url_to_path(url)
        self.assertEqual(result, url)
    
    def test_relative_path_unchanged(self):
        """Test that relative paths are unchanged"""
        url = "images/test.jpg"
        result = utils.convert_url_to_path(url)
        self.assertEqual(result, url)
    
    def test_case_sensitive_matching(self):
        """Test that URL matching is case sensitive"""
        url = "https://IMAGE.NEARZOOM.STORE/MEDIA/test.jpg"
        result = utils.convert_url_to_path(url)
        self.assertEqual(result, url)  # Should remain unchanged due to case difference
    
    def test_url_with_special_characters(self):
        """Test converting URL with special characters"""
        url = "https://image.nearzoom.store/media/images/test%20file%20(1).jpg"
        expected = "/home/catch/media/images/test%20file%20(1).jpg"
        result = utils.convert_url_to_path(url)
        self.assertEqual(result, expected)
    
    def test_url_with_unicode_characters(self):
        """Test converting URL with unicode characters"""
        url = "https://image.nearzoom.store/media/이미지/테스트.jpg"
        expected = "/home/catch/media/이미지/테스트.jpg"
        result = utils.convert_url_to_path(url)
        self.assertEqual(result, expected)


if __name__ == '__main__':
    unittest.main()