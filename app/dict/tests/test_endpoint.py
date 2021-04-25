from django.test import Client
from django.test import TestCase
from dict.models import KRL_ABC


class EndpointTestCase(TestCase):

    fixtures = ['articles.json',]

    def test_pointer(self):

        c = Client()
        for l in KRL_ABC:
            response = c.get('/' + l + '/1')
            self.assertEqual(200, response.status_code)


