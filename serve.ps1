$ErrorActionPreference = "Stop"
$Python = "C:\Users\22314\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$env:PYTHONPATH = "$PSScriptRoot"
& $Python -m classmind.api --host 127.0.0.1 --port 8766
