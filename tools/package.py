"""Create a clean GitHub-ready source ZIP and a per-file SHA256 manifest."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED_DIRS={'.git','build','work','__pycache__','.venv','.idea','.vscode'}
EXCLUDED_SUFFIXES={'.pyc','.pyo','.vvp','.exe','.elf','.vcd','.fst','.zip'}


def source_files():
    return sorted((p for p in ROOT.rglob('*') if p.is_file() and not p.is_symlink()
                   and not set(p.relative_to(ROOT).parts).intersection(EXCLUDED_DIRS)
                   and p.suffix not in EXCLUDED_SUFFIXES
                   and p.name not in {'SHA256SUMS','IMPLEMENTATION_CONTRACT.md'}),
                  key=lambda p:p.relative_to(ROOT).as_posix())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT.parent/'neurotile.zip')
    args=parser.parse_args();files=source_files()
    manifest=''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(ROOT).as_posix()+'\n'
                     for p in files)
    (ROOT/'SHA256SUMS').write_text(manifest,encoding='utf-8')
    output=args.output.resolve();output.parent.mkdir(parents=True,exist_ok=True)
    if output.is_relative_to(ROOT):
        raise ValueError('Place the source ZIP outside the project folder.')
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in [*files,ROOT/'SHA256SUMS']:
            archive.write(path,'neurotile/'+path.relative_to(ROOT).as_posix())
    print(f'{output}\n{len(files)+1} files; {output.stat().st_size:,} bytes')
    print('ZIP SHA256: '+hashlib.sha256(output.read_bytes()).hexdigest())


if __name__=='__main__':main()
