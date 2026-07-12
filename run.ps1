$ErrorActionPreference = "Stop"
$Python = "C:\Users\22314\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$env:PYTHONPATH = "$PSScriptRoot"
& $Python -m classmind.cli --input "$PSScriptRoot\data\demo.json" --output "$PSScriptRoot\output\schedule.json"
