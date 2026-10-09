import unittest

from fizzbuzz import fizzbuzz


class FizzBuzzTest(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(fizzbuzz(1), "1")
        self.assertEqual(fizzbuzz(7), "7")

    def test_fizz_and_buzz(self):
        self.assertEqual(fizzbuzz(9), "Fizz")
        self.assertEqual(fizzbuzz(10), "Buzz")

    def test_both(self):
        self.assertEqual(fizzbuzz(15), "FizzBuzz")
        self.assertEqual(fizzbuzz(45), "FizzBuzz")


if __name__ == "__main__":
    unittest.main()
