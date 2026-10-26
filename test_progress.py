"""
test_progress.py

Unit tests for progress.py — specifically the streak and meal-planner-unlock
logic, since those are the trickiest bits (they depend on "what day is it",
which is exactly the kind of thing that's annoying to test manually).

HOW TO RUN THIS:
    cd into the folder with progress.py and this file, then run:
        python3 -m unittest test_progress.py -v

    The "-v" just means "verbose" — it prints each test's name and
    PASS/FAIL instead of just a summary. Optional but nice while learning.

WHAT'S GOING ON:
    Python has a built-in testing toolkit called `unittest`. You write a
    class that inherits from unittest.TestCase, and every method whose
    name starts with `test_` gets run automatically as its own test.
    Inside each test, you call self.assertEqual(...), self.assertTrue(...)
    etc. to check "did the code actually do what I expected?".
"""

import unittest
from datetime import date, timedelta
import progress


class TestStreakLogic(unittest.TestCase):
    """Tests for the main daily streak (progress['streak'])."""

    def setUp(self):
        """
        setUp() runs automatically BEFORE every single test method below.
        We use it to build a brand-new, empty progress dict each time —
        so tests never leak state into each other (e.g. Test A's streak
        of 5 shouldn't still be sitting there when Test B starts).
        """
        self.progress = {
            "xp": 0,
            "level": 1,
            "streak": 0,
            "last_log_date": None,
            "badges": [],
            "total_logs": 0,
            "grocery_history": [],
            "meal_planner_streak": 0,
            "last_meal_planner_date": None,
            "meal_planner_unlocked": False,
        }
        # A fixed starting date so tests are 100% repeatable — never rely
        # on the real date.today() inside a test, or your test's result
        # could change depending on which day you happen to run it.
        self.day1 = date(2025, 6, 1)    

    def test_first_log_sets_streak_to_1(self):
        """Logging a goal for the very first time should set streak = 1."""
        progress.update_streak(self.progress, today=self.day1)
        self.assertEqual(self.progress["streak"], 1)   # assertEqual checks that the first argument equals the second; if not, the test fails.

    def test_three_consecutive_days_gives_streak_of_3(self):
        """This is your original question: does the streak actually hit 3?"""
        day2 = self.day1 + timedelta(days=1)  #time delta is a way to add or subtract days from a date
        day3 = self.day1 + timedelta(days=2)

        progress.update_streak(self.progress, today=self.day1)
        self.assertEqual(self.progress["streak"], 1)

        progress.update_streak(self.progress, today=day2)
        self.assertEqual(self.progress["streak"], 2)

        progress.update_streak(self.progress, today=day3)
        self.assertEqual(self.progress["streak"], 3)

    def test_skipping_a_day_resets_streak_to_1(self):
        """If the user logs day 1, then skips a day, streak should NOT be 2 — it resets."""
        day3 = self.day1 + timedelta(days=2)  # note: day 2 is skipped entirely

        progress.update_streak(self.progress, today=self.day1)
        progress.update_streak(self.progress, today=day3)

        self.assertEqual(self.progress["streak"], 1)

    def test_logging_twice_same_day_does_not_double_count(self):
        """Logging on the same day twice shouldn't bump the streak twice."""
        progress.update_streak(self.progress, today=self.day1)
        progress.update_streak(self.progress, today=self.day1)  # same day again

        self.assertEqual(self.progress["streak"], 1)

    def test_streak_3_badge_awarded_on_third_consecutive_day(self):
        """Full integration through on_daily_goal_met(): badge should appear on day 3, not before."""
        day2 = self.day1 + timedelta(days=1)
        day3 = self.day1 + timedelta(days=2)

        badges_day1 = progress.on_daily_goal_met(self.progress, protein_met=True, today=self.day1)
        badges_day2 = progress.on_daily_goal_met(self.progress, protein_met=True, today=day2)
        badges_day3 = progress.on_daily_goal_met(self.progress, protein_met=True, today=day3)

        self.assertNotIn("streak_3", badges_day1)
        self.assertNotIn("streak_3", badges_day2)
        self.assertIn("streak_3", badges_day3)


class TestMealPlannerUnlock(unittest.TestCase):
    """Tests for the separate 'meal planner' streak (needs protein AND carbs)."""

    def setUp(self):
        self.progress = {
            "xp": 0, "level": 1, "streak": 0, "last_log_date": None,
            "badges": [], "total_logs": 0, "grocery_history": [],
            "meal_planner_streak": 0, "last_meal_planner_date": None,
            "meal_planner_unlocked": False,
        }
        self.day1 = date(2025, 6, 1)

    def test_unlocks_after_3_days_of_hitting_both_goals(self):
        day2 = self.day1 + timedelta(days=1)
        day3 = self.day1 + timedelta(days=2)

        progress.update_meal_planner_streak(self.progress, protein_met=True, carbs_met=True, today=self.day1)
        self.assertFalse(self.progress["meal_planner_unlocked"])

        progress.update_meal_planner_streak(self.progress, protein_met=True, carbs_met=True, today=day2)
        self.assertFalse(self.progress["meal_planner_unlocked"])

        progress.update_meal_planner_streak(self.progress, protein_met=True, carbs_met=True, today=day3)
        self.assertTrue(self.progress["meal_planner_unlocked"])

    def test_missing_carbs_on_any_day_breaks_the_streak(self):
        day2 = self.day1 + timedelta(days=1)
        day3 = self.day1 + timedelta(days=2)
        day4 = self.day1 + timedelta(days=3)

        progress.update_meal_planner_streak(self.progress, protein_met=True, carbs_met=True, today=self.day1)
        progress.update_meal_planner_streak(self.progress, protein_met=True, carbs_met=False, today=day2)  # missed carbs
        self.assertEqual(self.progress["meal_planner_streak"], 0)

        # Even hitting both goals the next two days should only get us to day 2 of a NEW streak
        progress.update_meal_planner_streak(self.progress, protein_met=True, carbs_met=True, today=day3)
        progress.update_meal_planner_streak(self.progress, protein_met=True, carbs_met=True, today=day4)
        self.assertEqual(self.progress["meal_planner_streak"], 2)
        self.assertFalse(self.progress["meal_planner_unlocked"])

    def test_relocks_if_streak_breaks_after_unlocking(self):
        """Your spec says the feature should RELOCK if the streak breaks — testing that explicitly."""
        day2 = self.day1 + timedelta(days=1)
        day3 = self.day1 + timedelta(days=2)
        day4 = self.day1 + timedelta(days=3)

        progress.update_meal_planner_streak(self.progress, protein_met=True, carbs_met=True, today=self.day1)
        progress.update_meal_planner_streak(self.progress, protein_met=True, carbs_met=True, today=day2)
        progress.update_meal_planner_streak(self.progress, protein_met=True, carbs_met=True, today=day3)
        self.assertTrue(self.progress["meal_planner_unlocked"])  # unlocked on day 3

        progress.update_meal_planner_streak(self.progress, protein_met=True, carbs_met=False, today=day4)  # missed carbs
        self.assertFalse(self.progress["meal_planner_unlocked"])  # should relock


if __name__ == "__main__":
    unittest.main()