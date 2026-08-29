from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def test_deploy_static_site_fails_when_live_build_hash_does_not_match(tmp_path):
    root = Path("/home/ggb66/dev/EVH")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    live_html = tmp_path / "live.html"
    live_html.write_text(
        "<!doctype html><div>Build: 2026-08-29 00:00 EDT · 4e2bdf44c (4e2bdf44c) · Ready</div>",
        encoding="utf-8",
    )

    package_script = tmp_path / "package_static_site.sh"
    _write_executable(
        package_script,
        f"""#!/usr/bin/env bash
set -euo pipefail
rm -f "$OUTPUT_ZIP"
tmpdir="$(mktemp -d)"
mkdir -p "$tmpdir/EVHInstinctPDFRAG"
cp "{live_html}" "$tmpdir/EVHInstinctPDFRAG/index.html"
(cd "$tmpdir" && zip -q -r "$OUTPUT_ZIP" ./EVHInstinctPDFRAG)
rm -rf "$tmpdir"
""",
    )

    _write_executable(
        bin_dir / "aws",
        """#!/usr/bin/env bash
set -euo pipefail
exit 0
""",
    )
    _write_executable(
        bin_dir / "curl",
        f"""#!/usr/bin/env bash
set -euo pipefail
out=""
url=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o)
      out="$2"
      shift 2
      ;;
    -fsS)
      shift
      ;;
    *)
      url="$1"
      shift
      ;;
  esac
done
if [ -n "$out" ]; then
  cp "{live_html}" "$out"
else
  cat "{live_html}"
fi
""",
    )

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["PACKAGE_SCRIPT"] = str(package_script)
    env["OUTPUT_ZIP"] = str(tmp_path / "evh_site.zip")
    env["EXPECTED_SHORT_HASH"] = "f621b029a"
    env["AWS_REGION"] = "us-east-1"
    env["STATIC_SITE_BUCKET"] = "evh-instinct-pdf-rag-shell"

    proc = subprocess.run(
        [str(root / "scripts/deploy_static_site_s3.sh")],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
    )

    assert proc.returncode != 0
    assert "did not match expected commit hash f621b029a" in proc.stderr
