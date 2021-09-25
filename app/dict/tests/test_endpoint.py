from django.test import Client
from django.test import TestCase
from dict.models import KRL_ABC


class EndpointTestCase(TestCase):

    #todo: limited fixtures
    #fixtures = ['articles.json',]
    c = Client()

    def test_pointer(self):

        for l in KRL_ABC:
            response = self.c.get('/' + l + '/1')
            self.assertEqual(200, response.status_code)

    def test_search(self):

         response = self.c.get('/search/aig')
         self.assertEqual(200, response.status_code)
