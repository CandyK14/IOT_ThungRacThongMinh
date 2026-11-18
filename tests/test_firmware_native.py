import os
from pathlib import Path
import subprocess
import sys


def test_actual_firmware_logic_on_host(tmp_path):
    root=Path(__file__).resolve().parent.parent;exe=tmp_path/('logic.exe' if os.name=='nt' else 'logic')
    env=dict(os.environ,ZIG_GLOBAL_CACHE_DIR=str(root/'artifacts/zig-cache'),ZIG_LOCAL_CACHE_DIR=str(tmp_path/'zig-cache'))
    subprocess.run([sys.executable,'-m','ziglang','c++','-std=c++11','-Wall','-Wextra','-I',str(root/'include'),str(root/'tests/firmware_logic.cpp'),'-o',str(exe)],env=env,check=True,timeout=180,capture_output=True,text=True)
    result=subprocess.run([str(exe)],check=True,capture_output=True,text=True,timeout=10)
    assert 'Firmware logic PASS' in result.stdout
    print(result.stdout)
