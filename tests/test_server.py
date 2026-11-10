import http.client
import json
import threading
import unittest
from tools.serve import make_server


class DemoAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=make_server(port=0)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=5)
    def request(self,method,path,body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=30)
        data=json.dumps(body) if body is not None else None
        connection.request(method,path,data,headers or {})
        response=connection.getresponse();payload=response.read();status=response.status;connection.close()
        return status,payload
    def test_status_sample_and_reference(self):
        status,data=self.request('GET','/api/status');self.assertEqual(status,200)
        status_body=json.loads(data);self.assertEqual(status_body['model']['input_size'],64)
        status,data=self.request('POST','/api/infer',{'pixels':status_body['sample']['pixels'],'backend':'reference'})
        self.assertEqual(status,200);self.assertEqual(len(json.loads(data)['logits']),10)
    def test_rejects_bad_pixels_backend_and_sample_index(self):
        for body in [{'pixels':[0]*63},{'pixels':[17]*64},{'pixels':[True]*64},
                     {'pixels':[0]*64,'backend':'invented'}]:
            self.assertEqual(self.request('POST','/api/infer',body)[0],400)
        self.assertEqual(self.request('GET','/api/sample?index=-1')[0],400)
    def test_static_allowlist_and_cross_origin(self):
        self.assertEqual(self.request('GET','/../models/digits_q8.json')[0],404)
        self.assertEqual(self.request('POST','/api/infer',{'pixels':[0]*64},
                                     {'Origin':'https://example.com'})[0],403)
    def test_labs_are_real_reports(self):
        status,data=self.request('GET','/api/labs');self.assertEqual(status,200)
        result=json.loads(data);self.assertIn('workloads',result['memory'])
        self.assertIn('observer_accuracy',result['security']['isolated'])


if __name__=='__main__':unittest.main()
