from django.test import TestCase
from ..helpers import *

class KrlHelpersTestCase(TestCase):

    # N-GRAMS
    def test_ngram_1(self):

        self.assertEqual(
            'yö',
            create_ngram('yö, yöhyt', 3)
        )

    def test_normalization_1(self):
        self.assertEqual(
            'myödätuuli',
            normalization('müöd’ä|tuwl’i')
        )

    def test_normalization_2(self):
        self.assertEqual(
            'olgupiäluu',
            normalization('olgu|piä|luw')
        )

    def test_normailization_3(self):
        self.assertEqual(
            'leyhendeliečie',
            normalization('l’ewhend’el’iečie')
        )

    def test_normalization_4(self):
        self.assertEqual(
            'yhekšäntoista, yheksäntois’t’a',
            normalization('ühekšän|toista, üheks’än|tois’t’a')
        )

    def test_normalization_5(self):
        self.assertEqual(
            'vuate, vuatehut, vi̮ate',
            normalization('vuat||e, ~ehut, vi̮ate')
        )

    def test_normalization_5(self):
        self.assertEqual(
            'vuate, vuatehut, vi̮ate',
            normalization('vuat||e, ~ehut, vi̮ate')
        )

    # VARIANTS
    def test_get_variants_ves1(self):
        self.assertEqual(
            gen_word_variants('a˛i̮a'),
            {'aia', 'ai̮a'}
        )

    def test_get_variants_ves2(self):
        self.assertEqual(
            gen_word_variants('mi̮ajäicä I'),
            {'mi̮ajäicä', 'miajäicä'}
        )

    def test_get_variants_normal(self):
        self.assertEqual(
            gen_word_variants('mus||ta, ~tan’e'),
            {'musta', 'mustane'}
        )

    def test_get_variants_tilda(self):
        self.assertEqual(
            gen_word_variants('baba, ~z’en’i'),
            {'baba', 'babazeni'}
        )

    def test_get_variants_w(self):
        self.assertEqual(
            gen_word_variants('uwt||tua'),
            {'uuttua', 'uwttua', 'uvttua'}
        )

    def test_get_variants_complex1(self):
        self.assertEqual(
            gen_word_variants('jukko|puw'),
            {'jukkopuv', 'jukko', 'puw',
             'puv', 'jukkopuw', 'jukkopuu',
             'puu'}
        )

    def test_get_variants_complex2(self):
        self.assertEqual(
            gen_word_variants('jowdu|päivä'),
            {'jowdu', 'jowdupäivä', 'päivä',
             'jovdu', 'jovdupäivä', 'joudupäivä', 'joudu'}
        )

    def test_get_variants_yw(self):
        self.assertEqual(
            gen_word_variants('l’üwvä'),
            {'lüwvä', 'lyyvä', 'lyvvä',
             'lüvvä', 'lüüvä', 'lywvä'}
        )

    def test_get_variants_complex3(self):
        self.assertEqual(
            gen_word_variants('armas|miel’i|aigoman’e'),
            {'armas', 'mieli', 'aigomane',
             'armasmieliaigomane'}
        )

    def test_get_variants_wytilda(self):
        self.assertEqual(
            gen_word_variants('l’öwl’ü, ~n’e'),
            {'lövlü', 'löyly', 'löwlüne',
             'lövly', 'löwlü', 'löylyne',
             'lövlüne', 'löülü', 'löwly',
             'löülüne', 'löwlyne', 'lövlyne'}
        )

    def test_get_variants_complex_brackets(self):
        self.assertEqual(
            gen_word_variants('un’i|miel’is’s’ä(h)'),
            {'unimielissäh', 'uni', 'unimielissä',
             'mielissä', 'mielissäh'}
        )

    def test_get_variants_complex_yw(self):
        self.assertEqual(
            gen_word_variants('ühen|suwrun’e'),
            {'ühensuwrune', 'yhen', 'ühensuvrune',
             'yhensuvrune', 'yhensuwrune',
             'suvrune', 'yhensuurune',
             'ühen', 'suurune', 'suwrune',
             'ühensuurune'}
        )

    def test_get_variants_complex_w(self):
        self.assertEqual(
            gen_word_variants('jalga|möwkküne'),
            {'jalgamövkkyne', 'jalgamöwkkyne', 'jalgamövkküne',
             'möwkkyne', 'jalga', 'möwkküne',
             'jalgamöükküne', 'mövkkyne',
             'mövkküne', 'möükküne', 'möykkyne',
             'jalgamöwkküne', 'jalgamöykkyne'}
        )

    #todo: Add sorting by Krl test