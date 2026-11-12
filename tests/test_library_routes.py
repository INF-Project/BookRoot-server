import unittest
from unittest.mock import patch
from fastapi import HTTPException
from app.main import app
from app.api.routes.libraries import libraries, by_book, filters

class RouteTests(unittest.TestCase):
    def test_backend_routes_only(self):
        paths=app.openapi()['paths']
        self.assertIn('/api/libraries',paths)
        self.assertIn('/api/libraries/by-book/{isbn13}',paths)
        self.assertNotIn('/api/libraries/demo',paths)
        self.assertNotIn('/api/map-config',paths)
        self.assertFalse(any(getattr(route, 'path', '') in ('/', '/assets') for route in app.routes))
        params=paths['/api/libraries/by-book/{isbn13}']['get']['parameters']
        isbn=next(p for p in params if p['name']=='isbn13')
        self.assertEqual(isbn['schema']['pattern'],r'^[0-9]{13}$')
    def test_coordinate_pair(self):
        with self.assertRaises(HTTPException) as error:filters(latitude=36)
        self.assertEqual(error.exception.status_code,422)
    def test_missing_key(self):
        with patch('app.core.config.DATA4LIBRARY_KEY',''):
            with self.assertRaises(HTTPException) as error:libraries(filters())
        self.assertEqual(error.exception.status_code,503)
    def test_empty_holdings(self):
        with patch('app.api.routes.libraries.fetch_libraries',return_value=[]):
            result=by_book('9788936434267',filters())
        self.assertEqual(result.total,0)
        self.assertEqual(result.model_dump(), {'items': [], 'total': 0})
