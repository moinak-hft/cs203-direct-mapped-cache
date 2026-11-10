import sys
import unittest
from tools.common import ROOT
sys.path.insert(0,str(ROOT/'python'))
from neurotile.vision import compose_digits,segment_digits,validate_image


def rectangle(pixels,x,y,w,h,value=16,width=128):
    for yy in range(y,y+h):
        for xx in range(x,x+w):pixels[yy*width+xx]=value


class VisionTests(unittest.TestCase):
    def test_blank_has_no_forced_prediction(self):
        result=segment_digits([0]*8192,128,64,'double')
        self.assertEqual(result['status'],'blank');self.assertEqual(result['normalized'],[])
    def test_two_regions_sorted_and_normalized_with_mass_centering(self):
        pixels=[0]*8192;rectangle(pixels,10,9,12,30);rectangle(pixels,83,17,18,25)
        result=segment_digits(pixels,128,64,'auto')
        self.assertEqual(len(result['boxes']),2)
        self.assertLess(result['boxes'][0]['x'],result['boxes'][1]['x'])
        for image in result['normalized']:
            self.assertEqual(len(image),784);self.assertGreater(sum(image),0)
            mass=sum(image);cx=sum(i%28*v for i,v in enumerate(image))/mass
            cy=sum(i//28*v for i,v in enumerate(image))/mass
            self.assertLessEqual(abs(cx-13.5),.51);self.assertLessEqual(abs(cy-13.5),.51)
    def test_noise_does_not_become_a_third_digit(self):
        pixels=[0]*8192;rectangle(pixels,30,12,16,32);pixels[127]=16
        result=segment_digits(pixels,128,64,'auto')
        self.assertEqual(len(result['boxes']),1);self.assertTrue(result['warnings'])
    def test_manual_split_reveals_touching_crops(self):
        pixels=[0]*8192;rectangle(pixels,30,10,60,35)
        result=segment_digits(pixels,128,64,'double',split=60)
        self.assertEqual(len(result['boxes']),2);self.assertEqual(result['method'],'manual split column')
        self.assertEqual(result['boxes'][0]['width'],30)
    def test_single_mode_preserves_one_crop_and_missing_second_is_reported(self):
        pixels=[0]*8192;rectangle(pixels,10,10,8,28)
        self.assertEqual(len(segment_digits(pixels,128,64,'single')['boxes']),1)
        self.assertIn('only one',segment_digits(pixels,128,64,'double')['warnings'][-1])
    def test_composition_and_input_contracts(self):
        digit=[0]*784;rectangle(digit,10,4,5,20,width=28)
        image=compose_digits([digit,digit]);self.assertEqual(len(image),8192)
        self.assertEqual(len(segment_digits(image,128,64,'auto')['boxes']),2)
        for pixels,w,h in [([0]*64,128,64),([False]*8192,128,64),([0]*8192,100000,64)]:
            with self.assertRaises(ValueError):validate_image(pixels,w,h)
        with self.assertRaises(ValueError):segment_digits(image,128,64,split=True)
        with self.assertRaises(ValueError):compose_digits([digit,digit],width=28,height=28)


if __name__=='__main__':unittest.main()
