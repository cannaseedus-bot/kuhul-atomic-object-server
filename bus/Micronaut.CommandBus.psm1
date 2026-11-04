Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:MicronautRoot = Split-Path -Parent $PSScriptRoot
$script:CommandCatalog = @(
    [pscustomobject]@{ id = 'daemon-chat'; label = 'Daemon chat (embedded)'; description = 'Open the local React/ASX chat page inside a native WPF WebView2 window.' },
    [pscustomobject]@{ id = 'bot-orchestration'; label = 'Bot orchestration CLI'; description = 'Open the local bot orchestration command interface.' },
    [pscustomobject]@{ id = 'fel-svg-replay'; label = 'FEL to SVG replay'; description = 'Choose an events JSONL file and render SVG replay frames.' },
    [pscustomobject]@{ id = 'pi-learning-fold'; label = 'K''uhul pi learning fold'; description = 'Replay experience JSONL, relate records, apply bounded W-C attention, and retain a candidate trace.' },
    [pscustomobject]@{ id = 'cfpc-classify'; label = 'CFPC context-field classifier'; description = 'Classify neighborhood questions by intent, query-pattern coverage, and key/value gaps.' },
    [pscustomobject]@{ id = 'rpc-list'; label = 'RPC capability ports'; description = 'List RPC and host capability ports from the editable JSON registry or micronaut.bson.' },
    [pscustomobject]@{ id = 'rpc-call'; label = 'Call REST JSON route'; description = 'Invoke a route allowlisted in bus/rpc-api.json.' },
    [pscustomobject]@{ id = 'phase-runtime-api-start'; label = 'Start phase runtime REST API'; description = 'Start the loopback phase-runtime API and bind it to the RPC capability port.' },
    [pscustomobject]@{ id = 'static-site'; label = 'Host static site'; description = 'Serve a selected repository site directory on loopback.' },
    [pscustomobject]@{ id = 'bundle-build'; label = 'Build micronaut.bson'; description = 'Rebuild the DATA_ONLY Micronaut BSON bundle from current stack sources.' },
    [pscustomobject]@{ id = 'package-kso'; label = 'Build Field KSO'; description = 'Package neighborhood.jsonl and neighborhood.attention.jsonl into field.kso.' }
)

function Get-MicronautCommandCatalog {
    return @($script:CommandCatalog)
}

function Invoke-MicronautCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [ValidateSet('daemon-chat', 'bot-orchestration', 'fel-svg-replay', 'pi-learning-fold', 'cfpc-classify', 'rpc-list', 'rpc-call', 'phase-runtime-api-start', 'static-site', 'bundle-build', 'package-kso')]
        [string]$Id
    )

    switch ($Id) {
        'daemon-chat' {
            & (Join-Path $script:MicronautRoot 'Micronaut.ps1') StartOrchestrator
            if ($LASTEXITCODE -ne 0) { throw "Micronaut orchestrator start failed with exit code $LASTEXITCODE." }
            $project = Join-Path $script:MicronautRoot 'micronaut\daemon-chat-wpf\DaemonChatWpf.csproj'
            $exe = Join-Path $script:MicronautRoot 'micronaut\daemon-chat-wpf\bin\Release\net8.0-windows\MicronautDaemonChat.exe'
            if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
                $dotnet = Get-Command dotnet.exe -CommandType Application -ErrorAction Stop
                & $dotnet.Source build $project --configuration Release
                if ($LASTEXITCODE -ne 0) { throw "Embedded chat build failed with exit code $LASTEXITCODE." }
            }
            if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Embedded chat executable was not produced: $exe" }
            Start-Process -FilePath $exe -WorkingDirectory $script:MicronautRoot
        }
        'bot-orchestration' {
            $scriptPath = Join-Path $script:MicronautRoot 'micronaut\cli_interface.py'
            & python $scriptPath
            if ($LASTEXITCODE -ne 0) { throw "cli_interface.py exited with code $LASTEXITCODE." }
        }
        'fel-svg-replay' {
            $inputPath = Read-Host 'FEL events JSONL path (blank to cancel)'
            if ([string]::IsNullOrWhiteSpace($inputPath)) { Write-Host 'Cancelled.'; return }
            $inputPath = $inputPath.Trim().Trim('"')
            $resolvedInput = [System.IO.Path]::GetFullPath($inputPath)
            if (-not (Test-Path -LiteralPath $resolvedInput -PathType Leaf)) { throw "Input file not found: $resolvedInput" }
            $outputPath = Read-Host 'Output directory [replay_out]'
            $arguments = @{ Action = 'FelReplay'; InputPath = $resolvedInput; WriteSvg = $true }
            if (-not [string]::IsNullOrWhiteSpace($outputPath)) {
                # FelReplay derives its default output from the input if no output is set;
                # keep output routing in the established Micronaut action.
                $arguments.OutputPath = [System.IO.Path]::GetFullPath($outputPath.Trim().Trim('"'))
            }
            & (Join-Path $script:MicronautRoot 'Micronaut.ps1') @arguments
        }
        'pi-learning-fold' {
            $inputPath = Read-Host 'Experience JSONL path (blank to cancel)'
            if ([string]::IsNullOrWhiteSpace($inputPath)) { Write-Host 'Cancelled.'; return }
            $resolvedInput = [System.IO.Path]::GetFullPath($inputPath.Trim().Trim('"'))
            if (-not (Test-Path -LiteralPath $resolvedInput -PathType Leaf)) { throw "Input file not found: $resolvedInput" }
            $tracePath = Read-Host 'Candidate trace JSONL path [micronaut/pi-learning.trace.jsonl]'
            if ([string]::IsNullOrWhiteSpace($tracePath)) { $tracePath = Join-Path $script:MicronautRoot 'micronaut\pi-learning.trace.jsonl' }
            $tracePath = [System.IO.Path]::GetFullPath($tracePath.Trim().Trim('"'))
            & python (Join-Path $script:MicronautRoot 'micronaut\pi_learning.py') $resolvedInput --trace $tracePath
            if ($LASTEXITCODE -ne 0) { throw "π learning fold failed with exit code $LASTEXITCODE." }
        }
        'cfpc-classify' {
            $inputPath = Read-Host 'Neighborhood attention JSONL path [neighborhood.attention.jsonl]'
            if ([string]::IsNullOrWhiteSpace($inputPath)) { $inputPath = Join-Path $script:MicronautRoot 'neighborhood.attention.jsonl' }
            $resolvedInput = [System.IO.Path]::GetFullPath($inputPath.Trim().Trim('"'))
            if (-not (Test-Path -LiteralPath $resolvedInput -PathType Leaf)) { throw "Input file not found: $resolvedInput" }
            $outputPath = Read-Host 'CFPC result JSONL path [.micronaut/checkpoints/neighborhood-attention.cfpc.jsonl]'
            if ([string]::IsNullOrWhiteSpace($outputPath)) { $outputPath = Join-Path $script:MicronautRoot '.micronaut\checkpoints\neighborhood-attention.cfpc.jsonl' }
            $resolvedOutput = [System.IO.Path]::GetFullPath($outputPath.Trim().Trim('"'))
            & python (Join-Path $script:MicronautRoot 'micronaut\cfpc_classifier.py') $resolvedInput --output $resolvedOutput
            if ($LASTEXITCODE -ne 0) { throw "CFPC classification failed with exit code $LASTEXITCODE." }
        }
        'rpc-list' {
            $bundlePath = Read-Host 'BSON bundle path [micronaut.bson]'
            if ([string]::IsNullOrWhiteSpace($bundlePath)) { $bundlePath = 'micronaut.bson' }
            & (Join-Path $script:MicronautRoot 'Micronaut.ps1') RPCList -InputPath $bundlePath
        }
        'rpc-call' {
            $portName = Read-Host 'Logical RPC port (example: model-api)'
            $routeName = Read-Host 'Route id (example: models or chat-completions)'
            $payloadPath = Read-Host 'JSON request body path (blank for GET)'
            if ([string]::IsNullOrWhiteSpace($portName) -or [string]::IsNullOrWhiteSpace($routeName)) { Write-Host 'Cancelled.'; return }
            $arguments = @{ Action = 'RPCCall'; RpcPort = $portName.Trim(); Entry = $routeName.Trim() }
            if (-not [string]::IsNullOrWhiteSpace($payloadPath)) { $arguments.InputPath = $payloadPath.Trim().Trim('"') }
            & (Join-Path $script:MicronautRoot 'Micronaut.ps1') @arguments
        }
        'phase-runtime-api-start' {
            $portText = Read-Host 'Phase runtime API port [6170]'
            $port = 6170
            if (-not [string]::IsNullOrWhiteSpace($portText) -and -not [int]::TryParse($portText, [ref]$port)) { throw 'Port must be an integer.' }
            & (Join-Path $script:MicronautRoot 'Micronaut.ps1') StartPhaseRuntimeApi -PhaseRuntimePort $port
        }
        'static-site' {
            $sitePath = Read-Host 'Site directory (repository-local path)'
            if ([string]::IsNullOrWhiteSpace($sitePath)) { Write-Host 'Cancelled.'; return }
            $portText = Read-Host 'Loopback port [8080]'
            $port = 8080
            if (-not [string]::IsNullOrWhiteSpace($portText) -and -not [int]::TryParse($portText, [ref]$port)) { throw 'Port must be an integer.' }
            & (Join-Path $script:MicronautRoot 'Micronaut.ps1') StaticHost -InputPath $sitePath.Trim().Trim('"') -Port $port
        }
        'bundle-build' {
            & (Join-Path $script:MicronautRoot 'Micronaut.ps1') Bundle
        }
        'package-kso' {
            & (Join-Path $script:MicronautRoot 'Micronaut.ps1') Package -InputPath 'neighborhood.jsonl' -OutputPath 'field.kso' -All
        }
    }
}

Export-ModuleMember -Function Get-MicronautCommandCatalog, Invoke-MicronautCommand
