"""Deterministic host-side segmentation and MNIST normalization.

Image coordinates and digit boxes use half-open extents. Pixel values are ink
intensities0..16, bright ink on a dark background. This is image processing,
not an RTL image sensor or a learned text detector.
"""
from __future__ import annotations
from collections import deque
import math


def validate_image(pixels, width, height):
    if type(width) is not int or type(height) is not int:
        raise ValueError('Image dimensions must be integers.')
    if not 28 <= width <= 256 or not 28 <= height <= 128:
        raise ValueError('Supported canvas dimensions are28..256 by28..128.')
    if not isinstance(pixels,list) or len(pixels)!=width*height:
        raise ValueError('Pixel count must match width times height.')
    if any(type(value)is not int or not 0<=value<=16 for value in pixels):
        raise ValueError('Pixels must be integer ink intensities in0..16.')


def _clean(pixels,width,height):
    """Remove isolated tiny components using an8-connected foreground mask."""
    active={i for i,value in enumerate(pixels) if value>=2}
    components=[]
    while active:
        first=active.pop();queue=deque([first]);component=[first]
        while queue:
            current=queue.popleft();x=current%width;y=current//width
            for yy in range(max(0,y-1),min(height,y+2)):
                for xx in range(max(0,x-1),min(width,x+2)):
                    neighbor=yy*width+xx
                    if neighbor in active:
                        active.remove(neighbor);queue.append(neighbor);component.append(neighbor)
        components.append(component)
    largest=max(map(len,components),default=0)
    minimum=max(2,math.ceil(largest*.008))
    retained={i for component in components if len(component)>=minimum for i in component}
    # Keep faint antialiasing immediately next to retained ink.
    expanded=set(retained)
    for i in retained:
        x=i%width;y=i//width
        for yy in range(max(0,y-1),min(height,y+2)):
            for xx in range(max(0,x-1),min(width,x+2)):
                if pixels[yy*width+xx]:expanded.add(yy*width+xx)
    return [value if i in expanded else 0 for i,value in enumerate(pixels)],len(components)-sum(len(c)>=minimum for c in components)


def _box(pixels,width,height,left=0,right=None):
    right=width if right is None else right
    positions=[i for i,value in enumerate(pixels) if value>=2 and left<=i%width<right]
    if not positions:return None
    xs=[i%width for i in positions];ys=[i//width for i in positions]
    return {'x':min(xs),'y':min(ys),'width':max(xs)-min(xs)+1,'height':max(ys)-min(ys)+1}


def normalize_digit(pixels,width,height,box):
    """Fit to20x20, area-resample, and center ink mass inside28x28."""
    x0,y0,w,h=(box[k] for k in ('x','y','width','height'))
    scale=min(20/w,20/h)
    nw,nh=max(1,round(w*scale)),max(1,round(h*scale))
    output=[0]*784;ox=(28-nw)//2;oy=(28-nh)//2
    for dy in range(nh):
        top=dy*h/nh;bottom=(dy+1)*h/nh
        for dx in range(nw):
            left=dx*w/nw;right=(dx+1)*w/nw
            total=0.0
            for sy in range(math.floor(top),min(h,math.ceil(bottom))):
                wy=max(0,min(bottom,sy+1)-max(top,sy))
                for sx in range(math.floor(left),min(w,math.ceil(right))):
                    wx=max(0,min(right,sx+1)-max(left,sx))
                    total+=pixels[(y0+sy)*width+x0+sx]*wx*wy
            value=max(0,min(16,round(total/((right-left)*(bottom-top)))))
            output[(oy+dy)*28+ox+dx]=value
    mass=sum(output)
    if mass:
        cx=sum((i%28)*v for i,v in enumerate(output))/mass
        cy=sum((i//28)*v for i,v in enumerate(output))/mass
        tx=round(13.5-cx);ty=round(13.5-cy)
        centered=[0]*784
        for i,value in enumerate(output):
            xx=i%28+tx;yy=i//28+ty
            if 0<=xx<28 and 0<=yy<28:centered[yy*28+xx]=value
        output=centered
    return output


def segment_digits(pixels,width=128,height=64,mode='auto',split=None):
    """Return0..2 normalized crops, boxes and explicit ambiguity warnings."""
    validate_image(pixels,width,height)
    if mode not in ('single','double','auto'):raise ValueError('mode must be single, double or auto.')
    if split is not None and (type(split)is not int or not 0<split<width):
        raise ValueError('split must be an integer column strictly inside the canvas.')
    clean,removed=_clean(pixels,width,height);bounds=_box(clean,width,height)
    warnings=[]
    if removed:warnings.append(f'Removed {removed} isolated noise component(s).')
    if bounds is None:
        return {'status':'blank','normalized':[],'boxes':[],'split':None,
                'method':'empty foreground','warnings':['No digit-sized ink found.']}
    projection=[sum(clean[y*width+x] for y in range(height)) for x in range(width)]
    x0=bounds['x'];x1=x0+bounds['width'];chosen=None;method='single foreground crop'
    if mode!='single':
        # Favor a broad low-ink valley between significant ink on both sides.
        # Margin constraints are relative to the foreground, not the whole canvas.
        margin=max(1,round(bounds['width']*.12))
        candidates=list(range(x0+margin,x1-margin+1))
        center=(x0+x1)/2
        if candidates:
            minimum=min(projection[x] for x in candidates)
            low=[x for x in candidates if projection[x]==minimum]
            groups=[]
            for x in low:
                if not groups or x!=groups[-1][-1]+1:groups.append([x])
                else:groups[-1].append(x)
            valley=min(groups,key=lambda group:(-len(group),abs(sum(group)/len(group)-center)))
            candidate=round((valley[0]+valley[-1])/2)
            left=_box(clean,width,height,0,candidate);right=_box(clean,width,height,candidate,width)
            gap_width=len(valley) if minimum==0 else 0
            enough_ink=left and right and min(sum(projection[:candidate]),sum(projection[candidate:]))>=sum(projection)*.04
            clear_gap=minimum==0 and gap_width>=max(2,round(bounds['height']*.06))
            plausible_cut=clear_gap or minimum<=max(projection)*.45
            if enough_ink and (clear_gap or mode=='double' and plausible_cut):
                chosen=candidate;method='vertical projection gap' if clear_gap else 'minimum-ink split'
                if not clear_gap:warnings.append('No clear gap between digits; adjust the split if the crops look wrong.')
        if split is not None:
            chosen=split;method='manual split column'
    boxes=[bounds] if chosen is None else [_box(clean,width,height,0,chosen),_box(clean,width,height,chosen,width)]
    boxes=[box for box in boxes if box is not None]
    if mode=='double' and len(boxes)!=2:
        warnings.append('Two digits were requested, but only one foreground region was available.')
    if any(box['width']/box['height']>1.5 for box in boxes):
        warnings.append('A crop is unusually wide; touching digits may need a manual split.')
    return {'status':'ready','normalized':[normalize_digit(clean,width,height,box) for box in boxes],
            'boxes':boxes,'split':chosen,'method':method,'warnings':warnings}


def compose_digits(images,width=128,height=64):
    """Place1or2 genuine28x28 examples on the canvas without label-dependent edits."""
    if len(images) not in (1,2):raise ValueError('Expected one or two digit images.')
    if any(len(image)!=784 for image in images):raise ValueError('Each digit must have784 pixels.')
    if type(width)is not int or type(height)is not int or not 28<=height<=128 or not 28*len(images)<=width<=256:
        raise ValueError('The layout must have at least28 pixels per digit and a28..128 pixel height.')
    if any(type(value)is not int or not 0<=value<=16 for image in images for value in image):
        raise ValueError('Digit pixels must be integer intensities in0..16.')
    output=[0]*(width*height)
    cell_width=width//len(images)
    size=min(height-8,cell_width-8)
    scale=max(1,size//28);size=28*scale
    for digit,image in enumerate(images):
        left=digit*cell_width+(cell_width-size)//2;top=(height-size)//2
        for y in range(size):
            for x in range(size):output[(top+y)*width+left+x]=int(image[(y//scale)*28+x//scale])
    return output
