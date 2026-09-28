"""Compatibility entry point for the existing desktop shortcut; reuse one reader."""
import subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parent
subprocess.Popen([sys.executable,str(root/'launch.py')],cwd=root,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
