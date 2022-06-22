from django.test import TestCase
from ..models import Article, ArticleIndexWord

class ArticleTestCase(TestCase):

    def test_generate_vars_eule_with_norm(self):

        ewle = Article(id=1777,
                       word='ewle',
                       word_normalized='eule',
                       first_letter='E',
                       first_trigram='ewl',
                       source_id=1,
                       source_detalization=None)

        indx = (ArticleIndexWord(article=ewle, word=var) for var in ewle.word_index())
        testset = set(i.word for i in indx)
        self.assertSetEqual(
            {'ewle', 'eule', 'evle'},
            testset
        )

    def test_generate_vars_hyvin_with_norm(self):

        hyvin = Article(id=1777,
                   word='hüviin',
                   word_normalized='hyvin',
                   first_letter='H',
                   first_trigram='hyv',
                   source_id=1,
                   source_detalization=None)

        indx = (ArticleIndexWord(article=hyvin, word=var) for var in hyvin.word_index())
        testset = set(i.word for i in indx)

        self.assertSetEqual(
            {'hyvin', 'hyviin', 'hüviin', 'hüvin'},
            testset
        )


    def test_generate_vars_tuuli_with_norm(self):

        tuuli = Article(id=1777,
                   word='tuwl’||i, ~ut',
                   word_normalized='tuuli, tuulut',
                   first_letter='T',
                   first_trigram='tuw',
                   source_id=1,
                   source_detalization=None)

        indx = (ArticleIndexWord(article=tuuli, word=var) for var in tuuli.word_index())
        testset = set(i.word for i in indx)

        self.assertSetEqual(
            {'tuuli', 'tuulut', 'tuwli', 'tuvli', 'tuwlut', 'tuvlut'},
            testset
        )
