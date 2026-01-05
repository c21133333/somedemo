import unittest

import somedemo

class TestMain(unittest.TestCase):
    def test_main(self):
        self.assertTrue(hasattr(somedemo, "__package__"))

if __name__ == '__main__':
    unittest.main()
