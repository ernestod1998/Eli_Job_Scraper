"""Build a static Pages artifact from an explicit public-file allowlist."""
import argparse
from pathlib import Path
import shutil
import subprocess

PUBLIC_FILES = ("index.html", "triage.html", "all_jobs.json", "source_status.json")


def build(root, output, committed=False):
    output.mkdir(parents=True, exist_ok=False)
    for name in PUBLIC_FILES:
        if committed:
            data = subprocess.check_output(["git", "show", f"HEAD:{name}"], cwd=root)
            (output / name).write_bytes(data)
            continue
        source = root / name
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"Expected regular public file: {name}")
        shutil.copyfile(source, output / name)
    (output / ".nojekyll").touch()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("_site"))
    parser.add_argument("--committed", action="store_true", help="Read allowlisted files from HEAD, not the working directory")
    args = parser.parse_args()
    build(Path(__file__).resolve().parent, args.output, args.committed)
