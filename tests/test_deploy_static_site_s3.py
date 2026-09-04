from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


def _make_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def test_deploy_static_site_fails_when_live_build_hash_does_not_match(tmp_path):
    root = Path("/home/ggb66/dev/EVH/pony/worktrees/aj")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    _make_executable(
        fake_bin / "aws",
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = \"s3api\" ] && [ \"$2\" = \"head-bucket\" ]; then exit 0; fi\n"
        "if [ \"$1\" = \"s3api\" ] && [ \"$2\" = \"put-public-access-block\" ]; then exit 0; fi\n"
        "if [ \"$1\" = \"s3api\" ] && [ \"$2\" = \"put-bucket-policy\" ]; then exit 0; fi\n"
        "if [ \"$1\" = \"s3\" ] && [ \"$2\" = \"sync\" ]; then exit 0; fi\n"
        "if [ \"$1\" = \"s3\" ] && [ \"$2\" = \"website\" ]; then exit 0; fi\n"
        "echo \"unexpected aws call: $@\" >&2\n"
        "exit 1\n",
    )
    _make_executable(
        fake_bin / "curl",
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = \"-fsS\" ] && [ \"$2\" = \"$3\" ]; then\n"
        "  if [ $# -eq 3 ]; then\n"
        "    cat <<'EOF'\n"
        "<!doctype html><div>Build: 2026-08-29 00:00 EDT · 4e2bdf44c (4e2bdf44c) · Ready</div>\n"
        "EOF\n"
        "    exit 0\n"
        "  fi\n"
        "fi\n"
        "echo \"unexpected curl call: $@\" >&2\n"
        "exit 1\n",
    )
    _make_executable(
        fake_bin / "git",
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = \"-C\" ] && [ \"$3\" = \"rev-parse\" ] && [ \"$4\" = \"--short\" ] && [ \"$5\" = \"HEAD\" ]; then\n"
        "  printf '%s\\n' 'f621b029a'\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"$1\" = \"-C\" ] && [ \"$3\" = \"rev-parse\" ] && [ \"$4\" = \"--short\" ] && [ \"$5\" = \"HEAD\" ]; then\n"
        "  printf '%s\\n' 'f621b029a'\n"
        "  exit 0\n"
        "fi\n"
        "echo \"unexpected git call: $@\" >&2\n"
        "exit 1\n",
    )
    _make_executable(
        fake_bin / "unzip",
        "#!/usr/bin/env bash\nexit 0\n",
    )
    _make_executable(
        fake_bin / "zip",
        "#!/usr/bin/env bash\nexit 0\n",
    )
    _make_executable(
        fake_bin / "grep",
        "#!/usr/bin/env bash\ncommand grep \"$@\"\n",
    )
    _make_executable(
        fake_bin / "mkdir",
        "#!/usr/bin/env bash\ncommand mkdir \"$@\"\n",
    )

    site_dir = tmp_path / "website"
    target_dir = site_dir / "EVHInstinctPDFRAG"
    target_dir.mkdir(parents=True)
    (target_dir / "index.html").write_text(
        "<!doctype html><div>Build: __EVH_BUILD_STAMP__</div>",
        encoding="utf-8",
    )

    package_script = tmp_path / "package_static_site.sh"
    package_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "cp \"$SITE_DIR/EVHInstinctPDFRAG/index.html\" \"$ROOT_DIR/evh_site.zip\"\n",
        encoding="utf-8",
    )
    package_script.chmod(package_script.stat().st_mode | stat.S_IEXEC)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["SITE_DIR"] = str(site_dir)
    env["PACKAGE_SCRIPT"] = str(package_script)
    env["OUTPUT_ZIP"] = str(tmp_path / "evh_site.zip")
    env["STATIC_SITE_BUCKET"] = "evh-instinct-pdf-rag-shell"
    env["AWS_REGION"] = "us-east-1"
    env["EXPECTED_SHORT_HASH"] = "f621b029a"

    result = subprocess.run(
        [str(root / "scripts/deploy_static_site_s3.sh")],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "build stamp did not match expected commit hash" in result.stderr
