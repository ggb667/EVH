from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_package_static_site_injects_commit_hash_into_build_stamp(tmp_path, monkeypatch):
    root = Path("/home/ggb66/dev/EVH/pony/worktrees/aj")
    site_dir = tmp_path / "website"
    target_dir = site_dir / "EVHInstinctPDFRAG"
    target_dir.mkdir(parents=True)

    (target_dir / "index.html").write_text(
        "<!doctype html><div>Build: __EVH_BUILD_STAMP__</div>",
        encoding="utf-8",
    )

    output_zip = tmp_path / "evh_site.zip"
    env = os.environ.copy()
    env["SITE_DIR"] = str(site_dir)
    env["OUTPUT_ZIP"] = str(output_zip)

    subprocess.run(
        [str(root / "scripts/package_static_site.sh")],
        check=True,
        cwd=root,
        env=env,
    )

    extracted = tmp_path / "extracted"
    subprocess.run(["unzip", "-oq", str(output_zip), "-d", str(extracted)], check=True)
    html = (extracted / "EVHInstinctPDFRAG" / "index.html").read_text(encoding="utf-8")
    current_short_hash = subprocess.check_output(["git", "-C", str(root), "rev-parse", "--short", "HEAD"], text=True).strip()

    assert "Build: " in html
    assert current_short_hash in html
    assert "__EVH_BUILD_STAMP__" not in html
