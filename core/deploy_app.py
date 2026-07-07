# ================================================================
# Raven Framework
#
# Copyright (c) 2026 Raven Resonance, Inc.
# All Rights Reserved.
#
# ================================================================

"""
Deploy Raven applications: build .rav packages and optional CLI upload.

Compiles or copies Python sources, copies assets, zips the tree, provides
``deploy_app`` for local package creation, and ``handle_cli_deploy`` for
``deploy`` / ``deploy-pyc`` command-line flows.
"""

import glob
import os
import py_compile
import shutil
import sys
import time
import zipfile
from typing import List, Optional

from ..helpers.logger import get_logger
from ..helpers.utils_light import is_raven_device, load_config

log = get_logger("DeployApp")
_config = load_config()
PYTHON_VERSION_ON_RAVEN_DEVICE = _config["deployment"]["PYTHON_VERSION_ON_RAVEN_DEVICE"]
DEPLOY_ENDPOINT_URL = _config["deployment"]["DEPLOY_ENDPOINT_URL"]
ACCEPTING_DEPLOYMENTS = _config["deployment"].get("ACCEPTING_DEPLOYMENTS", True)
UPLOAD_TIMEOUT_S = 60


def _load_ravignore(app_path: str) -> List[str]:
    ravignore_path = os.path.join(app_path, ".ravignore")
    if not os.path.exists(ravignore_path):
        return []
    patterns = []
    with open(ravignore_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    if patterns:
        log.info(f"Loaded {len(patterns)} patterns from .ravignore")
    return patterns


def _should_ignore_path(rel_path: str, ignore_patterns: List[str]) -> bool:
    if not ignore_patterns:
        return False
    rel_path = rel_path.replace("\\", "/")
    if rel_path.startswith("./"):
        rel_path = rel_path[2:]
    for pattern in ignore_patterns:
        pattern = pattern.replace("\\", "/")
        if pattern.startswith("./"):
            pattern = pattern[2:]
        pattern_clean = pattern.rstrip("/")
        rel_path_clean = rel_path.rstrip("/")
        if rel_path_clean == pattern_clean or rel_path_clean.startswith(
            pattern_clean + "/"
        ):
            return True
    return False


def _filter_walk_iteration(
    root: str, dirs: List[str], app_path: str, ignore_patterns: List[str]
) -> bool:
    rel_root = os.path.relpath(root, app_path)
    if rel_root == ".":
        rel_root = ""
    filtered_dirs = []
    for d in dirs:
        if d == "__pycache__":
            continue
        dir_rel_path = os.path.join(rel_root, d).replace("\\", "/") if rel_root else d
        if not _should_ignore_path(dir_rel_path, ignore_patterns):
            filtered_dirs.append(d)
    dirs[:] = filtered_dirs
    return rel_root and _should_ignore_path(rel_root, ignore_patterns)


def compile_app(app_path: str, output_dir: str) -> bool:
    log.info(f"Compiling app at: {app_path}")
    os.makedirs(output_dir, exist_ok=True)
    ignore_patterns = _load_ravignore(app_path)
    python_files = []
    for root, dirs, files in os.walk(app_path):
        if _filter_walk_iteration(root, dirs, app_path, ignore_patterns):
            continue
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, app_path)
                if not _should_ignore_path(rel_path, ignore_patterns):
                    python_files.append(file_path)
    log.info(f"Found {len(python_files)} Python files to compile")
    for py_file in python_files:
        try:
            rel_path = os.path.relpath(py_file, app_path)
            output_file = os.path.join(output_dir, rel_path + "c")
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            py_compile.compile(py_file, output_file, doraise=True)
            log.debug(f"Compiled: {rel_path} -> {rel_path}c")
        except py_compile.PyCompileError as e:
            log.error(f"Failed to compile {py_file}: {e}")
            return False
    log.info("Successfully compiled files")
    return True


def copy_python_source(app_path: str, output_dir: str) -> bool:
    log.info(f"Copying Python source files from: {app_path}")
    os.makedirs(output_dir, exist_ok=True)
    ignore_patterns = _load_ravignore(app_path)
    python_files = []
    for root, dirs, files in os.walk(app_path):
        if _filter_walk_iteration(root, dirs, app_path, ignore_patterns):
            continue
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, app_path)
                if not _should_ignore_path(rel_path, ignore_patterns):
                    python_files.append(file_path)
    log.info(f"Found {len(python_files)} Python files to copy")
    for py_file in python_files:
        try:
            rel_path = os.path.relpath(py_file, app_path)
            output_file = os.path.join(output_dir, rel_path)
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            shutil.copy2(py_file, output_file)
            log.debug(f"Copied: {rel_path}")
        except Exception as e:
            log.error(f"Failed to copy {py_file}: {e}")
            return False
    log.info("Successfully copied Python source files")
    return True


def copy_assets(app_path: str, output_dir: str) -> bool:
    log.info("Copying assets...")
    ignore_patterns = _load_ravignore(app_path)
    asset_extensions = [
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".svg",
        ".wav",
        ".mp3",
        ".mp4",
        ".json",
        ".txt",
        ".md",
        ".sh",
    ]
    assets_copied = 0
    for root, dirs, files in os.walk(app_path):
        if _filter_walk_iteration(root, dirs, app_path, ignore_patterns):
            continue
        for file in files:
            if any(file.endswith(ext) for ext in asset_extensions):
                src_path = os.path.join(root, file)
                rel_path = os.path.relpath(src_path, app_path)
                if _should_ignore_path(rel_path, ignore_patterns):
                    continue
                dst_path = os.path.join(output_dir, rel_path)
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.copy2(src_path, dst_path)
                assets_copied += 1
                log.debug(f"Copied asset: {rel_path}")
    log.info(f"Copied {assets_copied} assets")
    return True


def create_rav_package(
    app_path: str, output_path: str, compile_pyc: bool = True
) -> bool:
    log.info(f"Creating .rav package: {output_path} (compile_pyc={compile_pyc})")
    temp_dir = f"/tmp/raven_deploy_{int(time.time())}"
    os.makedirs(temp_dir, exist_ok=True)
    try:
        if compile_pyc:
            if not compile_app(app_path, temp_dir):
                return False
        else:
            if not copy_python_source(app_path, temp_dir):
                return False
        if not copy_assets(app_path, temp_dir):
            return False
        requirements_path = os.path.join(app_path, "requirements.txt")
        if os.path.exists(requirements_path):
            shutil.copy2(requirements_path, temp_dir)
            log.info("Copied requirements.txt")
        build_run_sh_path = os.path.join(temp_dir, "run.sh")
        if not os.path.exists(build_run_sh_path):
            default_run_sh_path = os.path.join(os.path.dirname(__file__), "run.sh")
            if os.path.exists(default_run_sh_path):
                shutil.copy2(default_run_sh_path, build_run_sh_path)
                log.info("Added default run.sh")
            else:
                log.warning(
                    f"Default run.sh not found at {default_run_sh_path}; skipping"
                )
        package_stats = {
            "python_files": 0,
            "assets": {
                "images": 0,
                "audio": 0,
                "video": 0,
                "data": 0,
                "other": 0,
            },
            "requirements": False,
            "directories": set(),
            "total_files": 0,
            "file_list": [],
        }
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(temp_dir):
                if "raven_framework" in root:
                    log.info("Found raven_framework in source, ignoring")
                    continue
                for file in files:
                    file_path = os.path.join(root, file)
                    arc_path = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arc_path)
                    log.debug(f"Added to package: {arc_path}")
                    package_stats["file_list"].append(arc_path)
                    package_stats["total_files"] += 1
                    dir_name = os.path.dirname(arc_path)
                    if dir_name:
                        package_stats["directories"].add(dir_name)
                    if file.endswith((".pyc", ".py")):
                        package_stats["python_files"] += 1
                    elif file.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg")):
                        package_stats["assets"]["images"] += 1
                    elif file.endswith((".wav", ".mp3")):
                        package_stats["assets"]["audio"] += 1
                    elif file.endswith(".mp4"):
                        package_stats["assets"]["video"] += 1
                    elif file.endswith((".json", ".txt", ".md")):
                        if file == "requirements.txt":
                            package_stats["requirements"] = True
                        else:
                            package_stats["assets"]["data"] += 1
                    else:
                        package_stats["assets"]["other"] += 1
        package_size = os.path.getsize(output_path)
        size_mb = package_size / (1024 * 1024)
        details = [
            f"Package: {os.path.basename(output_path)}",
            f"Size: {size_mb:.2f} MB",
            f"Total files: {package_stats['total_files']}",
            f"Python files: {package_stats['python_files']}",
        ]
        asset_counts = [
            f"{k}: {v}" for k, v in package_stats["assets"].items() if v > 0
        ]
        if asset_counts:
            details.append(f"Assets ({', '.join(asset_counts)})")
        if package_stats["requirements"]:
            details.append("Includes requirements.txt")
        if package_stats["directories"]:
            dir_list = sorted(package_stats["directories"])
            if len(dir_list) <= 5:
                details.append(f"Directories: {', '.join(dir_list)}")
            else:
                details.append(
                    f"Directories: {len(dir_list)} total ({', '.join(dir_list[:3])}...)"
                )
        package_summary = f"Successfully created .rav package: {' | '.join(details)}"
        log.info(package_summary)
        print(f"\n{package_summary}", file=sys.stdout)
        if package_stats["file_list"]:
            print("\nFiles in package:", file=sys.stdout)
            for file_path in sorted(package_stats["file_list"]):
                print(f"  - {file_path}", file=sys.stdout)
        print()
        return True
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            log.info("Cleaned up temporary files")


def deploy_app(app_name: str = "dev", compile_pyc: bool = True) -> Optional[str]:
    version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    if version != PYTHON_VERSION_ON_RAVEN_DEVICE:
        error_msg = (
            f"FATAL ERROR: Make sure python version is {PYTHON_VERSION_ON_RAVEN_DEVICE}"
        )
        log.error(error_msg)
        print(f"ERROR: {error_msg}", file=sys.stderr)
        print(f"Current Python version: {version}", file=sys.stderr)
        return None
    if compile_pyc:
        log.info(f"Deploying app with Python version: {version} and compiling to .pyc")
        print(f"Using Python version: {version}", file=sys.stdout)
    old_files = glob.glob(os.path.join(".", "*.rav"))
    for f in old_files:
        filename = os.path.basename(f)
        try:
            os.remove(f)
            log.info(f"Deleted old file: {filename}")
        except Exception as e:
            log.warning(f"Could not delete old file {filename}: {e}")
    if not os.path.exists("main.py"):
        log.error("main.py not found in current directory")
        log.error("Please run this script from the same directory as main.py")
        return None
    timestamp = int(time.time())
    output_path = f"{app_name}_{version}_{timestamp}.rav"
    if create_rav_package(".", output_path, compile_pyc=compile_pyc):
        log.info(f"Package created: {os.path.abspath(output_path)}")
        log.info("=" * 50)
        log.info("DEPLOYMENT SUCCESSFUL!")
        return output_path
    else:
        log.error(f"Failed to create package for Python {version}")
        return None


def handle_cli_deploy(args: List[str], app_id: str, app_key: str) -> None:
    """
    If deploy or deploy-pyc was requested, run build + upload and return.
    Caller should return after calling this when deploy was requested.
    """
    if len(args) == 0 or args[0] not in ("deploy", "deploy-pyc"):
        return
    if is_raven_device():
        log.info("Deploy not available on device.")
        return
    if not ACCEPTING_DEPLOYMENTS:
        error_msg = "Not accepting deployments right now, contact Raven Resonance team to get access"
        log.warning(error_msg)
        print(f"{error_msg}", file=sys.stdout)
        return
    if app_id == "":
        error_msg = "Please add app_id to function call"
        log.error(error_msg)
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return
    if app_key == "":
        error_msg = "Please add app_key to function call"
        log.error(error_msg)
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return
    compile_pyc = args[0] == "deploy-pyc"
    log.info(f"Deployment mode: {'compiled (.pyc)' if compile_pyc else 'source (.py)'}")
    build_path = deploy_app(compile_pyc=compile_pyc)
    if not build_path:
        error_msg = "Failed to create build package, cannot upload"
        log.error(error_msg)
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return
    log.info(f"Build path: {build_path}")
    print(f"Build path: {build_path}", file=sys.stdout)
    data = {"app_id": app_id, "app_key": app_key}
    developer_end_point = DEPLOY_ENDPOINT_URL
    print("Uploading package...", file=sys.stdout)
    import requests

    try:
        with open(build_path, "rb") as build_file:
            files = {"rav_build": build_file}
            response = requests.post(
                url=developer_end_point,
                data=data,
                files=files,
                timeout=UPLOAD_TIMEOUT_S,
            )
    except requests.RequestException as e:
        error_msg = f"Upload failed: {e}"
        log.error(error_msg, exc_info=True)
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return
    upload_msg = f"Upload response status: {response.status_code}"
    log.info(upload_msg)
    if response.status_code == 200:
        print(f"{upload_msg} - Upload successful!", file=sys.stdout)
    else:
        print(f"{upload_msg} - Upload failed!", file=sys.stderr)
