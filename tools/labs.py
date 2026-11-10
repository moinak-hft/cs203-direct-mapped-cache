"""Regenerate the modeled memory and security reports from actual experiments."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'python'))
from neurotile.labs import run_all_labs
if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    output=root/'reports/labs.json';output.parent.mkdir(exist_ok=True)
    report=run_all_labs()
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'memory':report['memory']['summary'],'security':report['security']['summary']},indent=2))
    print('Full report: reports/labs.json')
