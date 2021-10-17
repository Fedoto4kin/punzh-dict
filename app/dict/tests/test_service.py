from django.test import TestCase
from dict.services import gen_word_variants, normalization
from dict.models import Article


class KrlServiceTestCase(TestCase):

    # TRIGRAMS
    def test_get_trigram_one(self):
        a1 = Article(word='a I', article_html='<b>Test 3</b>')
        a1.make_trigram()
        self.assertEqual(
            a1.first_trigram,
            'a'
        )

    def test_get_trigram_ves(self):
        a2 = Article(word='mi̮atičča', article_html='<b>Test 1</b>')
        a2.make_trigram()
        self.assertEqual(
            a2.first_trigram,
            'mua'
        )

    def test_get_trigram_normal(self):
        a3 = Article(word='abčüäö II', article_html='<b>Test 2</b>')
        a3.make_trigram()
        self.assertEqual(
            a3.first_trigram,
            'abč'
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


    # VARIANTS
    def test_get_variants_ves1(self):
        self.assertEqual(
            gen_word_variants('a˛i̮a'),
            {'aia', 'ai̮a'}
        )

    def test_get_variants_ves2(self):
        self.assertEqual(
            gen_word_variants('mi̮ajäičä I'),
            {'mi̮ajäičä', 'miajäičä'}
        )

    def test_get_variants_normal(self):
        self.assertEqual(
            gen_word_variants('muš||ta, ~tan’e'),
            {'mušta', 'muštane'}
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
            gen_word_variants('armaš|miel’i|aigoman’e'),
            {'armaš', 'mieli', 'aigomane',
             'armašmieliaigomane'}
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
            gen_word_variants('ühen|šuwrun’e'),
            {'ühenšuwrune', 'yhen', 'ühenšuvrune',
             'yhenšuvrune', 'yhenšuwrune',
             'šuvrune', 'yhenšuurune',
             'ühen', 'šuurune', 'šuwrune',
             'ühenšuurune'}
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
