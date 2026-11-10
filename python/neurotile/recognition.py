"""High-resolution single/two-digit recognition with identical integer backends."""
from __future__ import annotations
import time
from neurotile.hd_model import load_hd_model,predict_hd
from neurotile.vision import segment_digits


def recognize_image(pixels,width=128,height=64,mode='auto',backend='reference',split=None):
    if backend not in ('reference','c','rtl'):
        raise ValueError('backend must be reference, c or rtl.')
    start=time.perf_counter()
    segmentation=segment_digits(pixels,width,height,mode,split)
    features=segmentation.pop('normalized')
    if not features:
        return {'text':'','predictions':[],'digits':[],'status':'blank','batch_size':0,
                'segmentation':segmentation,'warnings':segmentation['warnings'],
                'backend':backend,'verified':False,'host_elapsed_ms':round((time.perf_counter()-start)*1000,3)}
    model=load_hd_model()
    if backend=='reference':
        results=[predict_hd(image,model) for image in features]
        report={'predictions':[result['prediction'] for result in results],
                'hidden':[result['hidden'] for result in results],'logits':[result['logits'] for result in results],
                'backend':'reference','verified':False,'batch_size':len(features),
                'cycle_scope':'Python integer reference; no hardware cycle measurement.'}
    elif backend=='c':
        from tools.hd_infer import c_infer_hd_batch
        report=c_infer_hd_batch(features,model)
    else:
        from tools.hd_infer import rtl_infer_hd_batch
        report=rtl_infer_hd_batch(features,model)
    digits=[]
    for i,prediction in enumerate(report['predictions']):
        logits=report['logits'][i];ranked=sorted(range(10),key=lambda j:logits[j],reverse=True)
        top,second=(logits[j] for j in ranked[:2])
        margin=(top-second)/max(1,abs(top),abs(second))
        digits.append({'prediction':prediction,'hidden':report['hidden'][i],'logits':logits,
                       'box':segmentation['boxes'][i],'normalized':features[i],'margin':round(margin,4),
                       'alternatives':[{'digit':j,'logit':logits[j]} for j in ranked[:3]]})
        if margin<.08:
            segmentation['warnings'].append(f'Digit {i+1} has a small score gap; inspect its crop and alternatives.')
    report.pop('hidden',None);report.pop('logits',None)
    report.update(text=''.join(str(prediction) for prediction in report['predictions']),digits=digits,
                  status='ready',segmentation=segmentation,warnings=segmentation['warnings'],
                  model='MNIST 784→64→10 INT8',host_elapsed_ms=round((time.perf_counter()-start)*1000,3),
                  preprocessing_scope='CPU image segmentation, area resampling and center-of-mass normalization; not RTL image processing.')
    return report
