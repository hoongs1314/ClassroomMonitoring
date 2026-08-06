param(
	[switch]$SkipFrontend
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $projectRoot 'backend'

Push-Location $projectRoot
try {
	$env:PYTHONPATH = $backendPath
	python -B -m unittest discover -s (Join-Path $backendPath 'tests') -p 'test_*.py'
	if ($LASTEXITCODE -ne 0) {
		exit $LASTEXITCODE
	}

	if (-not $SkipFrontend) {
		Push-Location (Join-Path $projectRoot 'web')
		try {
			npm run test
			if ($LASTEXITCODE -ne 0) {
				exit $LASTEXITCODE
			}
		}
		finally {
			Pop-Location
		}
	}
}
finally {
	Pop-Location
}
