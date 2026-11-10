import http.client
import json
import sys
import threading
import unittest
from tools.common import ROOT
sys.path.insert(0,str(ROOT/'python'))
from neurotile.recognition import recognize_image
from tools.serve import hd_sample,make_server


class RecognitionPipelineTests(unittest.TestCase):
    def test_official_pair_is_segmented_ordered_and_recognized(self):
        sample=hd_sample(0,2)
        result=recognize_image(sample['pixels'],mode='double')
        self.assertEqual(sample['label'],'72');self.assertEqual(result['text'],'72')
        self.assertEqual(result['batch_size'],2)
        for digit in result['digits']:
            self.assertEqual(len(digit['normalized']),784)
            self.assertEqual(len(digit['hidden']),64)
            self.assertEqual(len(digit['logits']),10)
            self.assertEqual(digit['prediction'],max(range(10),key=lambda i:digit['logits'][i]))
    def test_leading_zero_is_preserved_as_text(self):
        sample=hd_sample(3,2);result=recognize_image(sample['pixels'],mode='double')
        self.assertEqual(sample['label'],'04');self.assertEqual(result['text'],'04')
    def test_single_auto_and_blank_do_not_invent_a_second_digit(self):
        sample=hd_sample(0,1)
        result=recognize_image(sample['pixels'],mode='auto')
        self.assertEqual(result['text'],'7');self.assertEqual(len(result['digits']),1)
        result=recognize_image([0]*8192,backend='rtl')
        self.assertEqual(result['status'],'blank');self.assertEqual(result['text'],'')
        self.assertEqual(result['digits'],[]);self.assertNotIn('kernel_cycles',result)
    def test_bad_backend_is_rejected_even_for_blank_canvas(self):
        with self.assertRaises(ValueError):recognize_image([0]*8192,backend='fake')


class HighResolutionAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=make_server(port=0)
        cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.worker.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.worker.join(5)
    def request(self,method,path,body=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=30)
        connection.request(method,path,json.dumps(body)if body is not None else None)
        response=connection.getresponse();data=json.loads(response.read());status=response.status
        connection.close();return status,data
    def test_real_high_resolution_request_exceeds_legacy_body_limit_and_works(self):
        status,sample=self.request('GET','/api/hd/sample?index=0&digits=2')
        self.assertEqual(status,200);self.assertEqual(len(sample['pixels']),8192)
        body={**sample,'mode':'double','backend':'reference'}
        self.assertGreater(len(json.dumps(body)),16384)
        status,result=self.request('POST','/api/recognize',body)
        self.assertEqual(status,200);self.assertEqual(result['text'],'72')
        status,result=self.request('GET','/api/status')
        self.assertEqual(result['version'],'2.0');self.assertEqual(result['highres']['model']['input_size'],784)
    def test_malformed_images_and_samples_are_rejected(self):
        for body in [{'pixels':[0]*8192,'width':100000},
                     {'pixels':[17]*8192},{'pixels':[0]*8192,'mode':'triple'},
                     {'pixels':[0]*8192,'split':True}]:
            self.assertEqual(self.request('POST','/api/recognize',body)[0],400)
        for path in ['/api/hd/sample?digits=3','/api/hd/sample?index=10000']:
            self.assertEqual(self.request('GET',path)[0],400)


if __name__=='__main__':unittest.main()
