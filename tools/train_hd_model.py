"""Reproduce the28x28 MNIST model offline, or explicitly prepare source data."""
import argparse
import os
from pathlib import Path
import sys
for variable in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[variable]='1'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',type=int,default=2026)
    parser.add_argument('--epochs',type=int,default=40)
    parser.add_argument('--output-root',type=Path,default=ROOT)
    parser.add_argument('--prepare-data',action='store_true',help='Explicit network download and deterministic bundle preparation')
    parser.add_argument('--download-dir',type=Path,default=ROOT.parents[1]/'work/mnist-original')
    args=parser.parse_args()
    if args.epochs<1:parser.error('--epochs must be positive')
    if args.prepare_data:
        from neurotile.hd_dataset import prepare_hd_dataset
        print(prepare_hd_dataset(args.download_dir))
    from neurotile.hd_training import train_hd_and_export
    train_hd_and_export(args.output_root,args.seed,args.epochs)


if __name__=='__main__':main()
