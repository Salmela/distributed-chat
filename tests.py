import unittest

class TestStringMethods(unittest.TestCase):

    def test_works(self):
        self.assertEqual('foo', 'foo')

if __name__ == '__main__':
    unittest.main()
