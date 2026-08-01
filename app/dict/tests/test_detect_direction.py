from django.test import SimpleTestCase

from ..search import detect_direction


class DetectDirectionTestCase(SimpleTestCase):
    """
    Pins language detection for the search view. 'rus' iff the query contains
    any Cyrillic letter, else 'krl'. No DB: detect_direction is pure.

    Values verified against the function directly; the three cases marked
    below are exactly where the old first-char regex was wrong.
    """

    def test_cyrillic_is_rus(self):
        self.assertEqual("rus", detect_direction("быстро"))

    def test_latin_is_krl(self):
        self.assertEqual("krl", detect_direction("aiga"))

    def test_latin_with_wildcard_is_krl(self):
        # '?' / '.' are the fuzzy-search syntax; they must not sway direction.
        self.assertEqual("krl", detect_direction("ai?"))
        self.assertEqual("krl", detect_direction("ai."))

    def test_leading_dot_stays_krl(self):
        # OLD regex: leading '.' matched the class -> wrongly 'rus'. Fixed.
        self.assertEqual("krl", detect_direction(".aiga"))

    def test_leading_space_stays_krl(self):
        # OLD regex: leading whitespace matched \s -> wrongly 'rus'. Fixed.
        self.assertEqual("krl", detect_direction(" aiga"))

    def test_karelian_diacritics_are_krl(self):
        # Karelian special letters are Latin, not Cyrillic.
        self.assertEqual("krl", detect_direction("šoba"))
        self.assertEqual("krl", detect_direction("müöd’ä"))

    def test_uppercase_cyrillic_is_rus(self):
        self.assertEqual("rus", detect_direction("ЁЛКА"))
        self.assertEqual("rus", detect_direction("Быстро"))

    def test_mixed_input_favours_rus(self):
        # Deliberate behaviour change: any Cyrillic present -> Russian intent,
        # regardless of position. OLD regex judged by the first char only.
        self.assertEqual("rus", detect_direction("aiga быстро"))
        self.assertEqual("rus", detect_direction("быстро aiga"))

    def test_empty_is_krl(self):
        self.assertEqual("krl", detect_direction(""))
