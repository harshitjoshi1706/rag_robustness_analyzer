"""Materialize a fixed model snapshot; uses local HF cache before downloading."""

import argparse
import shutil
from pathlib import Path

from huggingface_hub import snapshot_download

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=Path("var/model"))
parser.add_argument("--revision", default="1110a243fdf4706b3f48f1d95db1a4f5529b4d41")
parser.add_argument("--offline", action="store_true")
args = parser.parse_args()
if args.output.exists():
    parser.error("Output exists; use an empty destination to avoid changing a frozen model")
source = snapshot_download(
    "sentence-transformers/all-MiniLM-L6-v2",
    revision=args.revision,
    local_files_only=args.offline,
    ignore_patterns=["onnx/*", "openvino/*", "*.h5", "*.ot"],
)
shutil.copytree(source, args.output, ignore=shutil.ignore_patterns(".cache"))
print(f"Prepared {args.output} from revision {args.revision}")
