"""Render the SoK overview and exact-count flow in the Edge/6G figure family.

ImageGen supplied composition drafts; all publication objects below are native
editable SVG geometry/text. Scientific content comes from the manuscript and
frozen E0 ledger. This script does not retrieve, recode, or reanalyse evidence.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
from matplotlib.font_manager import FontProperties, findfont
from xml.sax.saxutils import escape
from PIL import ImageFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / 'paper-sok-csur'
WORK = ROOT / 'artifacts/sok/concept-redesign'
FONT = Path(os.environ.get('SOK_FONT_DIR', '/System/Library/Fonts/Supplemental'))
FONTS = {}
for name, suffix in [('TimesNative',''),('TimesNativeI',' Italic'),
                     ('TimesNativeB',' Bold'),('TimesNativeBI',' Bold Italic')]:
    path = FONT/f'Times New Roman{suffix}.ttf'
    if not path.is_file():
        path = Path(findfont(FontProperties(family=['Times New Roman', 'Liberation Serif', 'DejaVu Serif'],
            weight='bold' if 'Bold' in suffix else 'normal',
            style='italic' if 'Italic' in suffix else 'normal')))
    FONTS[suffix] = path
    pdfmetrics.registerFont(TTFont(name,str(path)))
# Sampled from the actual Edge SVGs, rather than a generic pastel palette.
C = dict(warm='#F2F2F0', blue='#AAB8CC', light='#DCE3F0', beige='#F5CEA5',
         amber='#FFD78C', coral='#ED826F', pink='#F7D3D2', cyan='#AEE0E1',
         note='#3453A5', ink='#111111', white='#FFFFFF')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Drawing:
    """Four SVG units per final PDF point; labels remain live text."""
    def __init__(self, width, height, title, description, vertical_scale=1):
        self.ys=vertical_scale
        self.w, self.h = width, height*vertical_scale
        self.labels = []
        self.pdf_buffer=io.BytesIO()
        self.pdf=canvas.Canvas(self.pdf_buffer,pagesize=(width/4,self.h/4),
                               invariant=1,pageCompression=1,
                               initialFontName='TimesNativeI',initialFontSize=28)
        self.pdf.setTitle(title)
        self.pdf.setSubject(description)
        self.pdf.scale(.25,.25)
        self.pdf.translate(0,self.h)
        self.pdf.scale(1,-1)
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width/288:g}in" height="{self.h/288:g}in" viewBox="0 0 {width} {self.h}">',
                      f'<title>{escape(title)}</title><desc>{escape(description)}</desc>',
                      '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 Z" fill="#111111"/></marker></defs>']
        self.rect(0, 0, width, height, C['white'], stroke='none')

    def rect(self, x, y, w, h, fill, stroke=C['ink'], sw=2.3, rx=0, dash=None):
        y,h=y*self.ys,h*self.ys
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>')
        p=self.pdf; p.saveState(); p.setLineWidth(sw)
        if fill!='none':p.setFillColor(HexColor(fill))
        if stroke!='none':p.setStrokeColor(HexColor(stroke))
        if dash:p.setDash([float(v) for v in dash.split()])
        if rx:p.roundRect(x,y,w,h,rx,stroke=int(stroke!='none'),fill=int(fill!='none'))
        else:p.rect(x,y,w,h,stroke=int(stroke!='none'),fill=int(fill!='none'))
        p.restoreState()

    def line(self, points, arrow=False, both=False, dash=None, color=C['ink'], sw=2.6):
        points=[(x,y*self.ys) for x,y in points]
        pts=' '.join(f'{x},{y}' for x,y in points)
        self.parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linejoin="round"'+(' marker-end="url(#arrow)"' if arrow else '')+(' marker-start="url(#arrow)"' if both else '')+(f' stroke-dasharray="{dash}"' if dash else '')+'/>')
        p=self.pdf; p.saveState(); p.setStrokeColor(HexColor(color)); p.setLineWidth(sw); p.setLineJoin(1)
        if dash:p.setDash([float(v) for v in dash.split()])
        path=p.beginPath(); path.moveTo(*points[0])
        for xy in points[1:]:path.lineTo(*xy)
        p.drawPath(path)
        p.setDash([]); p.setFillColor(HexColor(color))
        for end,previous in ([(points[-1],points[-2])] if arrow else [])+([(points[0],points[1])] if both else []):
            dx,dy=end[0]-previous[0],end[1]-previous[1]
            length=math.hypot(dx,dy)
            if not length:continue
            ux,uy=dx/length,dy/length
            # Match SVG marker units and its 9/10 reference-point offset.
            tip=(end[0]+.6*sw*ux,end[1]+.6*sw*uy)
            base=(tip[0]-6*sw*ux,tip[1]-6*sw*uy)
            head=p.beginPath();head.moveTo(*tip)
            head.lineTo(base[0]-3*sw*uy,base[1]+3*sw*ux)
            head.lineTo(base[0]+3*sw*uy,base[1]-3*sw*ux)
            head.close();p.drawPath(head,stroke=0,fill=1)
        p.restoreState()

    def circle(self, x, y, r, fill=C['white'], sw=2.3):
        y*=self.ys
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{C["ink"]}" stroke-width="{sw}"/>')
        p=self.pdf;p.saveState();p.setLineWidth(sw);p.setStrokeColor(HexColor(C['ink']));p.setFillColor(HexColor(fill))
        p.circle(x,y,r,stroke=1,fill=1);p.restoreState()

    @staticmethod
    def font(size, bold=False, italic=True):
        suffix = ' Bold Italic' if bold and italic else ' Bold' if bold else ' Italic' if italic else ''
        return ImageFont.truetype(str(FONTS[suffix]), round(size*4))

    def text(self, x, y, value, size=30, bold=False, italic=True, anchor='middle', color=C['ink'], max_width=None):
        y*=self.ys
        f=self.font(size,bold,italic)
        width=f.getlength(value)/4
        if max_width is not None:
            assert width <= max_width, (value, width, max_width)
        left=x-(width/2 if anchor=='middle' else width if anchor=='end' else 0)
        box=f.getbbox(value, anchor='ls')
        bounds=[left+box[0]/4, y+box[1]/4, left+box[2]/4, y+box[3]/4]
        assert bounds[0]>=0 and bounds[2]<=self.w and bounds[1]>=0 and bounds[3]<=self.h, (value,bounds)
        self.labels.append(dict(text=value,font_pt=size/4,bounds_svg=bounds))
        self.parts.append(f'<text x="{x}" y="{y}" font-family="Times New Roman" font-size="{size}" font-weight="'+('bold' if bold else 'normal')+'" font-style="'+('italic' if italic else 'normal')+f'" text-anchor="{anchor}" fill="{color}">{escape(value)}</text>')
        name='TimesNative'+('BI' if bold and italic else 'B' if bold else 'I' if italic else '')
        p=self.pdf;p.saveState();p.translate(x,y);p.scale(1,-1)
        p.setFillColor(HexColor(color));p.setFont(name,size)
        if anchor=='middle':p.drawCentredString(0,0,value)
        elif anchor=='end':p.drawRightString(0,0,value)
        else:p.drawString(0,0,value)
        p.restoreState()

    def math(self, x, y, expr, size=32, anchor='middle'):
        # Underscores introduce exactly one subscript character, as in t_q.
        parts=[]
        for tok in re.findall(r'_.|[^_]+',expr):
            sub=tok.startswith('_'); text=tok[1:] if sub else tok
            s=size*.73 if sub else size
            parts.append((text,s,sub,self.font(s).getlength(text)/4))
        width=sum(p[3] for p in parts)
        cursor=x-(width/2 if anchor=='middle' else 0)
        for value,s,sub,w in parts:
            self.text(cursor,y+size*.22 if sub else y,value,s,anchor='start')
            cursor+=w

    def tab(self,x,y,label,size=30):
        width=self.font(size,True).getlength(label)/4+26
        self.rect(x,y,width,40,C['amber'])
        self.text(x+13,y+29,label,size,bold=True,anchor='start')

    def person(self,x,y,scale=1):
        self.circle(x+17*scale,y+14*scale,12*scale,C['amber'])
        self.parts.append(f'<path d="M{x},{(y+58*scale)*self.ys} v{-18*scale*self.ys} q{17*scale},{-20*scale*self.ys} {34*scale},0 v{18*scale*self.ys} Z" fill="{C["amber"]}" stroke="{C["ink"]}" stroke-width="2.3"/>')
        p=self.pdf;p.saveState();p.setLineWidth(2.3);p.setStrokeColor(HexColor(C['ink']));p.setFillColor(HexColor(C['amber']))
        q=p.beginPath();q.moveTo(x,(y+58*scale)*self.ys);q.lineTo(x,(y+40*scale)*self.ys)
        q.curveTo(x+34/3*scale,(y+(40-40/3)*scale)*self.ys,x+68/3*scale,(y+(40-40/3)*scale)*self.ys,x+34*scale,(y+40*scale)*self.ys)
        q.lineTo(x+34*scale,(y+58*scale)*self.ys);q.close();p.drawPath(q,fill=1,stroke=1);p.restoreState()

    def export(self,relative,preview):
        target=PAPER/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text('\n'.join(self.parts+['</svg>'])+'\n')
        pdf=target.with_suffix('.pdf')
        # Native PDF uses embedded TrueType fonts and deterministic metadata.
        # The same geometry drives SVG/PDF; neither file contains raster art.
        self.pdf.showPage();self.pdf.save();pdf.write_bytes(self.pdf_buffer.getvalue())
        renderer = shutil.which('rsvg-convert')
        if renderer:
            WORK.mkdir(parents=True,exist_ok=True)
            subprocess.run([renderer,'--width',str(round(self.w/288*300)),'--output',str(WORK/preview),str(target)],check=True)
        return dict(svg=str(target.relative_to(ROOT)),pdf=str(pdf.relative_to(ROOT)),
                    width_in=self.w/288,height_in=self.h/288,
                    svg_sha256=sha(target),pdf_sha256=sha(pdf),labels=self.labels)


def render_control():
    d=Drawing(972,738,'From semantic intent to a verified network outcome',
              'Three alternative interfaces feed controller checks. Only admitted actions execute. Interface ACK and verified outcome are different events. Timing is schematic. Reporting gates are separate evaluation questions.')
    d.rect(4,4,964,352,C['warm'],stroke='none')
    # A concrete participant/request and a separate supplied-context input.
    d.rect(17,20,218,189,C['white'])
    d.person(32,39,.9)
    d.text(139,51,'operator',30,bold=True)
    d.text(141,88,'“Restore',33)
    d.text(139,125,'the route”',33)
    d.text(126,179,'network intent',28,color=C['note'])
    d.rect(17,221,218,85,C['white'])
    d.text(126,253,'state · candidates',28,max_width=203)
    d.text(126,287,'constraints',28)
    d.line([(235,117),(262,117)],arrow=True)
    d.line([(235,264),(262,264)],arrow=True)
    # Alternatives share a perimeter, without arrows from one to the next.
    d.rect(265,18,293,290,'none',stroke=C['coral'],sw=5,rx=22)
    for y in [33,123,213]:
        d.rect(278,y,262,79,C['light'])
    for y,a,b in [(65,'Select','candidate'),(155,'Generate','config.'),(245,'Compute','predicate')]:
        d.text(347,y,a,31,bold=True,max_width=136)
        d.text(347,y+33,b,28,max_width=148)
    # The reference's choice bars and token sequence encode interface shape,
    # never experimental probabilities or measured performance.
    d.line([(439,95),(526,95)],sw=1.8)
    for x,h,fill in [(448,18,C['beige']),(471,43,C['coral']),(494,26,C['cyan'])]:
        d.rect(x,95-h,16,h,fill,sw=1.6)
    for x in [437,463,489]:
        d.rect(x,145,18,24,C['beige'],sw=1.5)
    d.text(523,166,'…',28,italic=False)
    d.math(484,255,'f(x)',34)
    # One result bus, rather than serial select/generate/compute stages.
    for y in [72,162,252]: d.line([(540,y),(569,y)],sw=2)
    d.line([(569,72),(569,252)],sw=2)
    d.line([(569,162),(597,162)],arrow=True)
    d.rect(600,20,175,286,C['blue'])
    d.text(687,58,'Checks',32,bold=True)
    for y,label in [(104,'State'),(142,'Feasibility'),(180,'Coverage')]:
        d.text(687,y,label,29,max_width=160)
    d.line([(610,200),(765,200)],sw=1.5)
    d.text(687,234,'admit',30,bold=True)
    d.text(687,269,'reject/refresh',28,max_width=163)
    # Input context reaches controller checks through a labelled dashed route.
    d.line([(126,306),(126,364),(583,364),(583,88),(598,88)],arrow=True,dash='6 5',sw=2)
    # Only the admitted branch is routed to execution.
    d.line([(731,228),(793,228),(793,69),(815,69)],arrow=True)
    d.rect(818,20,136,286,C['white'])
    d.text(886,54,'Submit',30,bold=True)
    for y in [72,87]:
        d.rect(859,y,54,12,C['blue'],sw=1.7)
        d.circle(867,y+6,1.5,C['ink'],sw=1)
    d.line([(886,107),(886,132)],arrow=True)
    d.text(886,165,'ACK',32,bold=True)
    d.line([(828,185),(944,185)],dash='5 4',sw=1.8)
    d.line([(886,193),(886,213)],arrow=True)
    d.circle(881,236,15,C['cyan'])
    d.line([(891,247),(905,261)],sw=4)
    d.text(886,291,'Verify',30,bold=True)
    d.tab(17,313,'intent + context',28)
    d.tab(274,313,'semantic interface',28)
    d.tab(599,313,'controller',28)
    d.tab(817,313,'execution',28)
    # Cumulative endpoint intervals start at arrival, not at the previous mark.
    d.rect(4,382,964,272,C['warm'],stroke='none')
    xs=[57,249,445,646,910]
    for x,t,label in zip(xs,['t_0','t_q','t_d','t_a','t_b'],['Arrival','Slot start','Accepted','ACK','Verified']):
        d.math(x,411,t,32)
        d.circle(x,429,4,C['ink'],sw=1)
        d.text(x,458,label,28)
    d.line([(57,429),(933,429)],arrow=True,dash='6 5',sw=2)
    for left,right,fill,label in zip(xs,xs[1:],[C['light'],C['coral'],C['beige'],C['cyan']],['queue','decision','submit','probe']):
        d.rect(left,471,right-left,34,fill,sw=1.5)
        d.text((left+right)/2,497,label,28)
    d.math(153,537,'Q = t_q − t_0',30)
    d.math(360,537,'D = t_d − t_q',30)
    for end,y,expr in [(646,562,'T_a = t_a − t_0'),(910,604,'T_b = t_b − t_0')]:
        d.line([(57,y),(end,y)],arrow=True,both=True,sw=1.9)
        for x in [57,end]:d.line([(x,y-9),(x,y+9)],sw=1.6)
        d.rect((57+end)/2-100,y-18,200,35,C['warm'],stroke='none')
        d.math((57+end)/2,y+9,expr,30)
    d.text(936,643,'timing sketch; not to scale',28,color=C['note'],anchor='end')
    # Gates are adjacent reporting questions with no sequential arrow.
    for x,w,fill,label in [(17,277,C['light'],'G1: Format'),(308,314,C['beige'],'G2: Task correctness'),(636,318,C['cyan'],'G3: Verified outcome')]:
        d.rect(x,671,w,48,fill)
        d.text(x+w/2,704,label,29,bold=True,max_width=w-15)
    return d.export('figures/family/control-boundary.svg','control-preview.png')


def screening_icon(d, kind, x, y):
    """Functional line drawings in the Edge/6G family, in a 62 × 58 box."""
    d.parts.append(f'<g aria-label="{kind}">')
    if kind in ['papers', 'search']:
        if kind=='papers':
            d.rect(x+12,y,40,48,C['light'],sw=1.9)
            d.rect(x+6,y+5,40,48,C['white'],sw=1.9)
        d.rect(x,y+10,40,48,C['white'],sw=2)
        for yy,ww in [(21,25),(30,25),(39,17)]:
            d.line([(x+7,y+yy),(x+7+ww,y+yy)],sw=2)
        if kind=='search':
            d.circle(x+40,y+32,14,C['light'],sw=2.3)
            d.line([(x+50,y+43),(x+61,y+56)],sw=4)
    elif kind=='citations':
        for points in [[(11,28),(45,9)],[(11,28),(45,48)]]:
            d.line([(x+xx,y+yy) for xx,yy in points],sw=2)
        for xx,yy,fill in [(11,28,C['white']),(45,9,C['light']),(45,48,C['light'])]:
            d.rect(x+xx-8,y+yy-8,16,18,fill,sw=2)
            d.line([(x+xx-4,y+yy-2),(x+xx+4,y+yy-2)],sw=1.7)
            d.line([(x+xx-4,y+yy+3),(x+xx+4,y+yy+3)],sw=1.7)
    elif kind=='filter':
        d.line([(x,y+3),(x+56,y+3),(x+34,y+29),
                (x+34,y+49),(x+23,y+56),(x+23,y+29),(x,y+3)],sw=2.5)
        d.line([(x+10,y+12),(x+46,y+12)],sw=2)
    elif kind=='compare':
        for xx in [0,35]:
            d.rect(x+xx,y+4,26,46,C['white'],sw=2)
            for yy in [16,25,34]:
                d.line([(x+xx+5,y+yy),(x+xx+21,y+yy)],
                       color=C['coral'] if xx and yy==25 else C['ink'],sw=2.5)
        d.line([(x+13,y+52),(x+13,y+58),(x+48,y+58),(x+48,y+52)],sw=2)
    elif kind=='folder':
        d.rect(x+3,y+5,44,40,C['white'],sw=2)
        d.rect(x,y+15,24,12,C['beige'],sw=2)
        d.rect(x,y+25,58,30,C['beige'],sw=2)
        d.line([(x+7,y+36),(x+31,y+36)],sw=2)
    elif kind=='linked':
        for xx,yy in [(0,0),(27,12)]:
            d.rect(x+xx,y+yy,25,33,C['white'],sw=1.8)
            d.line([(x+xx+5,y+yy+9),(x+xx+20,y+yy+9)],sw=1.8)
        d.line([(x+12,y+27),(x+12,y+40),(x+39,y+40)],sw=2.5)
    else:
        raise ValueError(kind)
    d.parts.append('</g>')


def render_screening():
    ledger=ROOT/'docs/sok/e0-current/analysis/screening-flow-source.json'
    c=json.loads(ledger.read_text())['counts']
    b,r,u,x=[c['initial_dispositions'][key] for key in ['B','R','U','X']]
    full=c['fulltext_dispositions']
    assert c['arxiv_hits']-c['arxiv_repeat_occurrences']==c['arxiv_unique']
    assert c['current_citations']+c['arxiv_unique']+c['targeted_additions']-c['cross_source_overlaps']==c['merged_records']
    assert c['merged_records']-b-x==c['fulltext_candidates']==r+u
    assert c['fulltext_candidates']-full['scope_background']==c['retained_source_ids']==full['scope_eligible']+full['linked_version']
    assert c['retained_source_ids']-c['multi_source_groups']==c['reading_groups']
    assert c['reading_groups']-c['excluded_groups']==c['included_families']
    assert c['retained_source_ids']-c['excluded_groups']==c['included_source_ids']
    assert sum(c['scope_kinds'].values())==c['coded_scopes']==231+174
    method=(PAPER/'sections/review-method.tex').read_text()
    assert '231' in method and '174' in method and '18' in method
    d=Drawing(2016,680,'Bounded corpus formation and independent coding',
              'Counts distinguish discovery records, retained source versions, reading groups, included families and paired coded scopes. Screening is assistant-led. Researcher 1 and Researcher 2 independently code, then adjudicate. No personal names are displayed.')
    for y,h in [(4,160),(182,208),(405,271)]:
        d.rect(4,y,2008,h,C['warm'],stroke='none')
    # Three independent inputs. The 159 hits belong only to arXiv.
    for px,pw,kind in [(24,306,'papers'),(358,404,'search'),(790,340,'citations')]:
        d.rect(px,18,pw,86,C['beige'])
        screening_icon(d,kind,px+18,32)
    d.text(215,53,f"{c['current_citations']} cited",38,bold=True)
    d.text(215,89,'records',31)
    d.text(596,53,f"{c['arxiv_unique']} unique arXiv IDs",34,bold=True,max_width=308)
    d.text(596,89,f"{c['arxiv_hits']} hits − {c['arxiv_repeat_occurrences']} repeats",29,color=C['note'])
    d.text(999,53,f"{c['targeted_additions']} additions",36,bold=True)
    d.text(999,89,'targeted discovery',30,max_width=239)
    for cx in [177,560,960]:d.line([(cx,104),(cx,117)],sw=2.3)
    d.line([(177,117),(1170,117),(1170,94),(1514,94)],arrow=True)
    d.text(1337,39,f"−{c['cross_source_overlaps']} cross-source",31)
    d.text(1337,72,'overlaps',31)
    d.rect(1518,18,470,86,C['blue'])
    screening_icon(d,'folder',1535,30)
    d.text(1790,54,f"{c['merged_records']} merged records",38,bold=True,max_width=370)
    d.text(1790,89,'after source deduplication',30,max_width=370)
    d.tab(20,124,'1. Discovery + merge',32)
    d.text(1980,151,'bounded through 28 September 2026',30,color=C['note'],anchor='end')
    # Retention goes left to right; exclusions branch down from their true stage.
    d.rect(24,197,360,87,C['blue'])
    screening_icon(d,'filter',42,212)
    d.text(240,233,f"{c['merged_records']} records",38,bold=True)
    d.text(240,268,'title / abstract screen',30,max_width=265)
    d.rect(600,197,424,87,C['blue'])
    d.text(812,233,f"{c['fulltext_candidates']} full-text candidates",35,bold=True,max_width=408)
    d.text(812,268,f'{r} retained + {u} boundary',30)
    d.rect(1234,197,408,87,C['blue'])
    d.text(1438,233,f"{c['retained_source_ids']} source/version records",33,bold=True,max_width=392)
    d.text(1438,268,f"{full['scope_eligible']} eligible + {full['linked_version']} linked versions",30,max_width=392)
    d.rect(1770,197,218,87,C['blue'])
    d.text(1879,233,str(c['reading_groups']),39,bold=True)
    d.text(1879,268,'reading groups',30)
    for start,end in [(384,600),(1024,1234),(1642,1770)]:d.line([(start,240),(end-4,240)],arrow=True)
    d.line([(487,240),(487,292)],arrow=True)
    d.rect(386,295,282,70,C['pink'],stroke=C['coral'],dash='6 4')
    d.text(527,321,f'−{b} background',29)
    d.text(527,353,f'−{x} out of scope',29)
    d.line([(1130,240),(1130,309)],arrow=True)
    d.rect(1006,312,248,50,C['pink'],stroke=C['coral'],dash='6 4')
    d.text(1130,346,f"−{full['scope_background']} background",30)
    screening_icon(d,'linked',1680,187)
    d.text(1706,300,f"{c['multi_source_groups']} pairs",28)
    d.text(1706,331,'grouped',28,color=C['note'])
    d.tab(20,348,'2. Screening + grouping',31)
    d.text(1438,373,'assistant-led',30,color=C['note'])
    # Independent author inputs meet only at the adjudication node.
    d.rect(24,439,234,90,C['blue'])
    d.text(141,478,str(c['reading_groups']),39,bold=True)
    d.text(141,514,'reading groups',30)
    d.line([(258,484),(288,484),(288,443),(313,443)],arrow=True)
    d.line([(288,484),(288,521),(313,521)],arrow=True)
    for y,number in [(411,1),(489,2)]:
        d.rect(317,y,288,64,C['white'])
        d.person(329,y+6,.72)
        d.text(478,y+27,f'Researcher {number}',32,bold=True,max_width=238)
        d.text(478,y+57,'independent coding',29,max_width=238)
        d.line([(605,y+32),(630,y+32),(630,484)],sw=2.6)
    d.line([(630,484),(654,484)],arrow=True)
    d.rect(658,439,382,90,C['beige'])
    screening_icon(d,'compare',674,451)
    d.text(884,478,'Compare answers',33,bold=True,max_width=288)
    d.text(884,514,'adjudicate scope',31,max_width=288)
    d.line([(1040,484),(1440,484)],arrow=True)
    d.line([(1244,484),(1244,548)],arrow=True)
    d.rect(1100,551,288,78,C['pink'],stroke=C['coral'],dash='6 4')
    d.text(1244,583,f"−{c['excluded_groups']} reading group",31)
    d.text(1244,616,'CPU forecasts only',29)
    d.rect(1444,432,544,111,C['amber'])
    screening_icon(d,'folder',1461,447)
    d.text(1750,481,f"{c['included_families']} included families",40,bold=True,max_width=442)
    d.text(1716,528,f"{c['included_source_ids']} source IDs · {c['distinct_bibliography_entries']} bibliography entries",30,max_width=525)
    d.text(1716,579,'Task and version scopes remain distinct',29,color=C['note'])
    # Place coding-unit and paired-answer details inside the author stage,
    # without presenting scope-aligned rechecks as an unchanged initial pass.
    d.text(315,589,f"{c['included_families']} families → {c['coded_scopes']} coded scopes",33,bold=True,max_width=575)
    d.text(315,625,f"{c['scope_kinds']['new_step']} step definitions + {c['scope_kinds']['same_step_scope']} linked scopes",30,max_width=575)
    d.text(849,567,'231 initially comparable',31,bold=True,max_width=382)
    d.text(849,602,'+ 174 aligned rechecks',31,bold=True,max_width=382)
    d.text(849,637,'= 405 answer pairs',30,color=C['note'])
    d.text(1716,620,'18 evidence fields',33,bold=True,max_width=520)
    d.text(1716,656,'field-level reporting and agreement',30)
    d.tab(20,636,'3. Independent coding + author adjudication',31)
    result=d.export('figures/screening-flow.svg','screening-preview.png')
    result['source_ledger_sha256']=sha(ledger)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--only',choices=['control','screening'])
    args=parser.parse_args()
    WORK.mkdir(parents=True,exist_ok=True)
    results={}
    if args.only in [None,'control']:results['control-boundary']=render_control()
    if args.only in [None,'screening']:results['screening-flow']=render_screening()
    receipt=WORK/'geometry.json'
    previous=json.loads(receipt.read_text()) if receipt.exists() else {}
    previous.update(results)
    receipt.write_text(json.dumps(previous,indent=2)+'\n')
    # Keep existing provenance bindings usable after a targeted regeneration.
    manifest_path=PAPER/'figure-manifest.yml'
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text())
        for row in manifest['artifacts']:
            if row['artifact_id'] in results:
                row['sha256']=results[row['artifact_id']]['pdf_sha256']
                row['generator_sha256']=sha(Path(__file__))
                row['placement'].update(width_in=results[row['artifact_id']]['width_in'],
                                        height_in=results[row['artifact_id']]['height_in'])
        manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    family_path=ROOT/'artifacts/sok/style-migration/figures.json'
    if family_path.exists():
        family=json.loads(family_path.read_text())
        for row in family['artifacts']:
            if 'control-boundary' in row['path'] and 'control-boundary' in results:
                row['sha256']=sha(PAPER/row['path'])
        family['concept_renderer']={'path':str(Path(__file__).relative_to(ROOT)),
                                    'sha256':sha(Path(__file__))}
        family_path.write_text(json.dumps(family,indent=2)+'\n')
    imports_path=ROOT/'artifacts/sok/restructure/asset-imports.json'
    if imports_path.exists() and 'screening-flow' in results:
        imports=json.loads(imports_path.read_text())
        for row in imports['sources']:
            if row['paper'] in ['figures/screening-flow.pdf','tables/screening-flow.tex']:
                row['paper_sha256']=sha(PAPER/row['paper'])
        imports_path.write_text(json.dumps(imports,indent=2)+'\n')
    print(json.dumps({name:{k:v for k,v in row.items() if k!='labels'} for name,row in results.items()},indent=2))


if __name__=='__main__':
    main()
