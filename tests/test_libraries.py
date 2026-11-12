import io
import json
import unittest
from unittest.mock import patch
from app.clients.data4library import request_json, LibraryAPIError
from app.schemas.libraries import Library
from app.services.distance import distance_km
from app.services.libraries import normalize, fetch_libraries, select_libraries

class LibrariesTests(unittest.TestCase):
    def test_distance(self):
        self.assertEqual(distance_km(36,127,36,127),0)
        self.assertAlmostEqual(distance_km(0,0,0,1),111.195,places=2)

    def test_filter_sort_and_missing_coordinates(self):
        items=[Library(library_code='01', name='가까움', address='', district='유성구', latitude=36,longitude=127),
               Library(library_code='02', name='멀리',address='',district='유성구',latitude=37,longitude=127),
               Library(library_code='03',name='좌표없음',address='',district='유성구'),
               Library(library_code='04',name='다른구',address='',district='동구')]
        result=select_libraries(items,'유성구',36,127)
        self.assertEqual([x.library_code for x in result.items],['01','02','03'])
        self.assertEqual(result.total,3)
        self.assertIsNone(items[0].distance_km)

    def test_invalid_upstream_coordinates(self):
        raw={'libCode':'001','libName':'테스트','address':'대전광역시 유성구 대학로','latitude':'NaN','longitude':'127'}
        result=normalize(raw)
        self.assertEqual(result.library_code,'001')
        self.assertEqual(result.district,'유성구')
        self.assertIsNone(result.latitude)

    def test_all_pages_before_sort(self):
        pages=[{'numFound':2,'libs':[{'lib':{'libCode':'001','libName':'먼 곳','latitude':'37','longitude':'127'}}]},
               {'numFound':2,'libs':[{'lib':{'libCode':'002','libName':'가까운 곳','latitude':'36','longitude':'127'}}]}]
        with patch('app.services.libraries.request_json',side_effect=pages) as call:
            result=select_libraries(fetch_libraries('9788936434267'),latitude=36,longitude=127)
        self.assertEqual(result.items[0].library_code,'002')
        self.assertEqual(call.call_args_list[0].args[1]['isbn'],'9788936434267')
        self.assertEqual(call.call_args_list[1].args[1]['pageNo'],2)

    def test_incomplete_page_fails(self):
        with patch('app.services.libraries.request_json',return_value={'numFound':2,'libs':[]}):
            with self.assertRaises(LibraryAPIError):fetch_libraries()

    def test_client_errors_and_secret(self):
        with patch('app.core.config.DATA4LIBRARY_KEY','secret'), patch('app.clients.data4library.urlopen',side_effect=TimeoutError):
            with self.assertRaises(LibraryAPIError) as error:request_json('libSrch',{})
            self.assertEqual(error.exception.status_code,504)
            self.assertNotIn('secret',str(error.exception))
        with patch('app.core.config.DATA4LIBRARY_KEY',''):
            with self.assertRaises(LibraryAPIError) as error:request_json('libSrch',{})
            self.assertEqual(error.exception.status_code,503)

    def test_json_and_provider_error(self):
        for payload, success in [({'response':{'numFound':0,'libs':[]}},True),({'response':{'error':'secret details'}},False),({'wrong':{}},False)]:
            with patch('app.core.config.DATA4LIBRARY_KEY','secret'), patch('app.clients.data4library.urlopen',return_value=io.BytesIO(json.dumps(payload).encode())):
                if success:self.assertEqual(request_json('libSrch',{})['numFound'],0)
                else:
                    with self.assertRaises(LibraryAPIError) as error:request_json('libSrch',{})
                    self.assertNotIn('secret',str(error.exception))

if __name__=='__main__':unittest.main()
