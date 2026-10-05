"""Verify style migration against frozen evidence and independent old table output."""
from pathlib import Path
import hashlib
import json
import logging
import re
import tempfile
from collections import Counter
import pdfplumber
from sok_e0_tables import reader_tables

ROOT=Path(__file__).resolve().parents[1]
PAPER=ROOT/'paper-sok-csur'
OUT=ROOT/'artifacts/sok/style-migration'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def plain(s, filename=''):
    # Trailing row padding is presentation, never part of a numeric cell.
    s=re.sub(r'\s*\\addlinespace(?:\[[^\]]*\])?\s*$', '', s)
    s=re.sub(r'\$([0-9]+(?:\.[0-9]+)?)\\times10\^\{([+-]?\d+)\}\$',lambda m:m[1]+'e'+str(int(m[2])),s)
    s=re.sub(r'(?<![\w.])([0-9]+(?:\.[0-9]+)?)e([+-]?\d+)(?![\w.])',lambda m:m[1]+'e'+str(int(m[2])),s)
    if filename=='sixg-published-radio.tex':
        s=s.replace('Lower violation','Opposite direction').replace('Higher violation','Expected direction')
    if filename=='rq-a-native.tex':s=s.replace(' & --- & ',' & N/A & ')
    if filename=='rq-a-length.tex':
        for display,source in [('Padding',r'pad\_16384'),('Irrelevant text','padded'),('Repetition','repeated')]:
            s=s.replace(' & '+display+' & ',' & '+source+' & ')
    if filename in ['rq-d-capacity.tex','rq-d-capacity-edge-high.tex']:
        for seconds in ['0.3','0.6','1.2']:
            s=s.replace('Fixed '+seconds+' s & ','fixed-latency-'+seconds+' & ')
    aliases={r'\jev':'Jev',r'\sokjev':'Jev',r'\deepseek':'DeepSeek',r'\semif':'SemIf',
        r'\glm':'GLM 5.3',r'\sokglm':'GLM' if filename.startswith('retained-') else 'GLM 4.7',
        r'\qwenflash':'Qwen 3.8',r'\qwenjson':'Qwen JSON',
        r'\sokqwen':'Qwen' if filename.startswith('retained-') else 'Qwen 3.5',
        r'\gemini':'Gemini',r'\anyjev':'AnyJev',r'\laya':'Laya'}
    for macro,alias in aliases.items():s=s.replace(macro+' & ',alias+' & ')
    s=re.sub(r'\\(?:rowcolor|cellcolor)\{[^{}]*\}','',s)
    s=re.sub(r'\\textcolor\{[^{}]*\}\{([^{}]*)\}',r'\1',s)
    return re.sub(r'\\textbf\{([^{}]*)\}',r'\1',s)
def numeric_rows(p):
    rows=[]
    for line in p.read_text().splitlines():
        if ' & ' not in line or '\\caption' in line or '\\multicolumn' in line: continue
        if line.startswith('Model & '):continue
        text=plain(line,p.name); cells=text.split(' & ')
        # Technology labels such as "5G" are prose, not numeric result cells.
        number = r'^\s*(?:[−-]?\d+(?:\.\d+)?(?:e[+−-]?\d+)?(?![\w.])|N/A\b|\$[<−-]?\d)'
        if not any(re.search(number,c) for c in cells[1:]): continue
        rows.append(text)
    return rows

def numeric_blocks(p):
    """Allow model reordering only inside the same contiguous condition block."""
    blocks=[];block=[]
    eligible=set(numeric_rows(p))
    for line in p.read_text().splitlines():
        value=plain(line,p.name)
        if value in eligible:block.append(value)
        elif block:blocks.append(Counter(block));block=[]
    if block:blocks.append(Counter(block))
    return blocks

def main():
    baseline=json.loads((OUT/'baseline.json').read_text())
    for filename,expected in baseline['frozen_evidence'].items():
        assert sha(ROOT/filename)==expected,filename
    script=ROOT/'scripts/sok_manuscript_assets.py'
    checked={}
    reader_outputs=reader_tables(json.loads((ROOT/'docs/sok/e0-current/analysis/results.json').read_text()))
    reader_checked={}
    # Never execute the original importer against the canonical manuscript.
    # Its declared paper and receipt destinations are both redirected first.
    with tempfile.TemporaryDirectory(prefix='jev-sok-numeric-') as directory:
        q=Path(directory);paper=q/'paper';out=q/'receipt'
        (paper/'tables').mkdir(parents=True);(paper/'supplement').mkdir()
        code=script.read_text().replace("PAPER = ROOT / 'paper-sok-csur'", 'PAPER = Path('+repr(str(paper))+')').replace("OUT = ROOT / 'artifacts/sok/restructure'", 'OUT = Path('+repr(str(out))+')')
        assert "PAPER = ROOT / 'paper-sok-csur'" not in code
        assert "OUT = ROOT / 'artifacts/sok/restructure'" not in code
        exec(compile(code,str(script),'exec'),{'__file__':str(script),'__name__':'style_numeric_baseline'})
        for source in (paper/'tables').glob('*.tex'):
            current=PAPER/'tables'/source.name
            if source.name in reader_outputs:
                assert current.read_text()==reader_outputs[source.name],source.name
                reader_checked[source.name]=18 if source.name=='e0-categories-table.tex' else 15
                continue
            expected,actual=numeric_rows(source),numeric_rows(current)
            a,b=numeric_blocks(current),numeric_blocks(source)
            assert a==b,(source.name,[(dict(x-y),dict(y-x)) for x,y in zip(a,b) if x!=y],len(a),len(b))
            checked[source.name]=len(actual)
        supplements=list((paper/'supplement').glob('*'))
        for source in supplements:
            assert source.read_bytes()==(PAPER/'supplement'/source.name).read_bytes(),source.name
    logging.getLogger('pdfminer').setLevel(logging.ERROR)
    bounds=[]
    for p in (PAPER/'figures/family').glob('*.pdf'):
        with pdfplumber.open(p) as doc:
            page=doc.pages[0]
            outside=[w['text'] for w in page.extract_words() if w['x0']<-.2 or w['x1']>page.width+.2 or w['top']<-.2 or w['bottom']>page.height+.2]
            if outside: bounds.append(dict(asset=p.name,text=outside))
    assert not bounds,bounds
    result=dict(status='PASS_STYLE_EVIDENCE_CHECK',tables=checked,numeric_rows=sum(checked.values()),
        reader_e0_tables=reader_checked,
        supplements_compared=len(supplements),frozen_evidence_files=len(baseline['frozen_evidence']),
        panel_word_bounds_exceptions=bounds,
        method='Isolated original-table regeneration; compare exact model/value rows within each native condition block after expanding declared display aliases and removing presentation wrappers. Model order may change within a block. Reader-facing E0 tables are checked separately against all 18 category distributions and 15 combined multi-select options from frozen results, including coder selection marginals. Also compare full supplement bytes, frozen source hashes and vector-panel text bounds.')
    (OUT/'numeric-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
