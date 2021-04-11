from django.test import TestCase
from dict.services import gen_word_variants
from dict.models import Article


class KrlServiceTestCase(TestCase):

    def test_get_trigram(self):

        a1 = Article(word='a I', article_html='<b>Test 3</b>')
        a1.make_trigram()
        self.assertEqual(
            a1.first_trigram,
            'a'
        )

        a2 = Article(word='mi̮atičča', article_html='<b>Test 1</b>')
        a2.make_trigram()
        self.assertEqual(
            a2.first_trigram,
            'mua'
        )

        a3 = Article(word='abčüäö II', article_html='<b>Test 2</b>')
        a3.make_trigram()
        self.assertEqual(
            a3.first_trigram,
            'abč'
        )

    def test_new_orthography(self):

        self.assertEqual(1, 1)

    def test_get_variants(self):


        self.assertEqual(
            gen_word_variants('a˛i̮a'),
            {'aia', 'ai̮a'}
        )

        self.assertEqual(
            gen_word_variants('muš||ta, ~tan’e'),
            {'mušta', 'muštane'}
        )

        self.assertEqual(
            gen_word_variants('baba, ~z’en’i'),
            {'baba', 'babazeni'}
        )

        self.assertEqual(
            gen_word_variants('mi̮ajäičä I'),
            {'mi̮ajäičä', 'miajäičä'}
        )

        self.assertEqual(
            gen_word_variants('uwt||tua'),
            {'uuttua', 'uwttua', 'uvttua'}
        )

        self.assertEqual(
            gen_word_variants('jukko|puw'),
            {'jukkopuv', 'jukko', 'puw',
             'puv', 'jukkopuw', 'jukkopuu',
             'puu'}
        )

        self.assertEqual(
            gen_word_variants('jowdu|päivä'),
            {'jowdu', 'jowdupäivä', 'päivä',
             'jovdu', 'jovdupäivä', 'joudupäivä', 'joudu'}
        )

        self.assertEqual(
            gen_word_variants('l’üwvä'),
            {'lüwvä', 'lyyvä', 'lyvvä',
             'lüvvä', 'lüüvä', 'lywvä'}
        )

        self.assertEqual(
            gen_word_variants('armaš|miel’i|aigoman’e'),
            {'armaš', 'mieli', 'aigomane',
             'armašmieliaigomane'}
        )

        self.assertEqual(
            gen_word_variants('l’öwl’ü, ~n’e'),
            {'lövlü', 'löyly', 'löwlüne',
             'lövly', 'löwlü', 'löylyne',
             'lövlüne', 'löülü', 'löwly',
             'löülüne', 'löwlyne', 'lövlyne'}
        )

        self.assertEqual(
            gen_word_variants('un’i|miel’is’s’ä(h)'),
            {'unimielissäh', 'uni', 'unimielissä',
             'mielissä', 'mielissäh'}
        )

        self.assertEqual(
            gen_word_variants('ühen|šuwrun’e'),
            {'ühenšuwrune', 'yhen', 'ühenšuvrune',
             'yhenšuvrune', 'yhenšuwrune',
             'šuvrune', 'yhenšuurune',
             'ühen', 'šuurune', 'šuwrune',
             'ühenšuurune'}
        )

        self.assertEqual(
            gen_word_variants('jalga|möwkküne'),
            {'jalgamövkkyne', 'jalgamöwkkyne', 'jalgamövkküne',
             'möwkkyne', 'jalga', 'möwkküne',
             'jalgamöükküne', 'mövkkyne',
             'mövkküne', 'möükküne', 'möykkyne',
             'jalgamöwkküne', 'jalgamöykkyne'}
        )





