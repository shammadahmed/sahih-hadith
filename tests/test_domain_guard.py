import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import unittest
from domain_guard import classify_islamic_domain

class DomainGuardTests(unittest.TestCase):
    def test_islamic_questions_are_allowed(self):
        for q in [
            "What does Sahih al-Bukhari say about intentions?",
            "Explain the difference between sahih and hasan hadith",
            "Tell me about the life of Imam al-Bukhari",
            "What is the ruling on zakat in Islam?",
        ]:
            with self.subTest(q=q):
                self.assertTrue(classify_islamic_domain(q)[0])

    def test_unrelated_questions_are_rejected(self):
        for q in [
            "How do I write a Python function?",
            "What is the weather in Karachi?",
            "Build a Laravel app for coaches",
            "Who won the football match?",
        ]:
            with self.subTest(q=q):
                self.assertFalse(classify_islamic_domain(q)[0])

if __name__ == "__main__":
    unittest.main()
