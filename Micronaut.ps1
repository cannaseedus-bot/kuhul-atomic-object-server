[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('Help', 'Health', 'Models', 'Host', 'Bot', 'Chat', 'AgentCreate', 'AgentList', 'MicronautList', 'MicronautInspect', 'NumpyTrain', 'NumpyGenerate', 'Todo', 'Advisor', 'EditWorker', 'Distill', 'Attention', 'Package', 'Validate', 'Bundle', 'BundleList', 'BundleGet', 'BundleRun', 'RPCList', 'RPCCall', 'StaticHost', 'FelVerify', 'FelReplay', 'MetaFold', 'FoldDemo', 'StartOrchestrator', 'StartController', 'StartResearch', 'StartPhaseRuntimeApi', 'StartXslRuntimeApi', 'Services', 'StopService', 'Worker')]
    [string]$Action = 'Help',

    [ValidateSet('Bot', 'Distill', 'Attention', 'Package', 'Validate', 'FelVerify', 'FelReplay', 'MetaFold')]
    [string]$Task,

    [string]$Word,
    [string]$Prompt,
    [string]$Context,
    [string]$Entry,
    [ValidateSet('', 'local', 'ollama', 'lmstudio')]
    [string]$Backend = '',
    [string]$Model,
    [ValidateSet('', 'ollama', 'lmstudio')]
    [string]$EmbeddingBackend = '',
    [string]$EmbeddingModel,
    [string]$Endpoint,
    [string]$InputPath,
    [string]$OutputPath,
    [string]$EntryPath,
    [string[]]$ScriptArgs = @(),
    [string]$WorkerId,
    [ValidateSet('orchestrator', 'controller', 'research', 'static-site', 'phase-runtime-api', 'xsl-runtime-api')]
    [string]$ServiceName,
    [string]$AgentId,
    [string]$TaskId,
    [string]$AgentName,
    [string]$AgentSystemPrompt,
    [string]$StreamId,
    [string]$RegistryPath = 'micronaut\docs\micronaut.registry.json',
    [string]$RpcRegistryPath = 'bus\rpc-api.json',
    [string]$RpcPort,
    [int]$Port = 8080,
    [int]$PhaseRuntimePort = 6170,
    [int]$XslRuntimePort = 6171,
    [string]$PolicyPin,
    [string]$AbiPin,
    [string]$RegistryPolicyPin,
    [string]$RegistryAbiPin,
    [switch]$WriteSvg,
    [switch]$WriteBin,
    [switch]$Execute,
    [switch]$Apply,
    [switch]$Meta,
    [switch]$WithAttention,
    [switch]$Recursive,
    [switch]$All,
    [int]$MaxDepth = 0,
    [int]$MaxNodes = 0,
    [double]$DurationMinutes = 30,
    [double]$AttentionTemperature = 0.07,
    [int]$TrainingEpochs = 5,
    [int]$TrainingStride = 2,
    [double]$LearningRate = 0.005,
    [int]$RandomSeed = 42,
    [int[]]$PromptTokens = @(),
    [string]$PromptText = 'Hello GPT',
    [string]$CorpusText = 'Hello GPT! Writing neural networks entirely from scratch using only NumPy arrays.',
    [string]$CheckpointPath,
    [int]$MaxNewTokens = 10,
    [int]$MaxSeqLen = 16,
    [double]$GenerationTemperature = 0.8,
    [int]$TopK = 0,
    [int]$QueryHeads = 4,
    [int]$KVHeads = 2,
    [ValidateSet('cpu', 'opencl')]
    [string]$OptimizerBackend = 'cpu',
    [double]$WeightDecay = 0.0,
    [string]$OpenCLDevice
)

$ErrorActionPreference = 'Stop'
$script:RepoRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$script:Python = $null
$script:DefaultLocalModel = 'C:\Users\canna\.lmstudio\models\lmstudio-community\gemma-3-1B-it-QAT-GGUF\gemma-3-1B-it-QAT-Q4_0.gguf'
$script:DefaultOllamaModel = 'qwen3.5:4b'
$script:DefaultEmbeddingModel = 'embeddinggemma:latest'
$script:DefaultLmStudioModel = 'liquid/lfm2.5-1.2b'
$script:DefaultEmbeddingModelLmStudio = 'text-embedding-nomic-embed-text-v1.5'

function Write-Usage {
    @'
Micronaut.ps1 — controlled K'UHUL Python tool host

Actions:
  Health                                      Check Python and model endpoints
  Models [-Backend ollama|lmstudio|local]     List available models / local model path
  Host [-Backend ollama] [-Model <name>]      Ensure the Ollama API is running
  Bot -Prompt <text> [-Backend ollama|lmstudio] Call the Daemon Bot on the hosted model
  Chat [-AgentId daemon-bot]                      Start the interactive XAIML/model CLI
  AgentCreate -AgentId <id> -AgentName <name>    Scaffold a user-owned daemon agent
  AgentList                                      List agents registered by the local server
  MicronautList [-Recursive]                    List declarative micronaut definitions
  MicronautInspect -EntryPath <file>             Read one definition (JSON or source text)
  NumpyTrain [-InputPath <text-file>] [-CheckpointPath <file.safetensors>] [-OptimizerBackend cpu|opencl] [-WeightDecay <n>] [-OpenCLDevice <name>]  Train from raw text
  NumpyGenerate [-CheckpointPath <file.safetensors>] [-PromptText <text> | -PromptTokens <ids>] [-MaxNewTokens <n>] [-TopK <n>]  Generate text/token IDs
  Todo [-TaskId <id>]                            Project tasks from the manifest-linked todo.md
  Advisor [-TaskId <id>] [-Prompt <question>]    Ask the configured Qwen tool model for a read-only plan
  EditWorker -TaskId <id> [-Apply]               Run one bounded todo task; -Apply enables exact-anchor edits
  Distill -Word <word> [-Recursive] [-WithAttention]  Write neighborhood.jsonl; optionally embed only this word
  Attention [-Entry <word|glyph>] [-EmbeddingBackend ollama|lmstudio] [-EmbeddingModel <name>]  Write attention sidecar JSONL
  Package [-Entry <word|glyph> | -All]         Build a field or complete neighborhood field.kso
  Validate -InputPath <file.kso>              Validate KSO1 data-only package
  Bundle                                        Rebuild micronaut.bson from local runtime sources
  BundleList [-InputPath micronaut.bson]        List bundled files and hashes
  BundleGet -EntryPath <relative-path>          Read a UTF-8 entry from micronaut.bson
  BundleRun -EntryPath mu-py\<script.py> -Execute  Launch one bundled source script with host Python
  RPCList [-InputPath micronaut.bson]             List logical RPC and host capability ports
  RPCCall -RpcPort <name> -Entry <route> [-InputPath payload.json]  Call a registered REST JSON route
  StaticHost -InputPath <site-directory> [-Port 8080]  Host static files on loopback
  FelVerify -InputPath <events.jsonl>          Verify FEL, optionally replay proof outputs
  FelReplay -InputPath <events.jsonl>          Generate SVG replay artifacts
  MetaFold -InputPath <roots.jsonl> -StreamId <id> -PolicyPin <sha256> -AbiPin <sha256>  Write attestations
  FoldDemo                                      Run the interactive fold-system demonstration
  StartController                             Start registry-gated WS controller on loopback
  StartResearch                               Start registry/policy-gated research WS bot
  StartPhaseRuntimeApi [-PhaseRuntimePort 6170] Start the phase runtime REST API on loopback
  StartXslRuntimeApi [-XslRuntimePort 6171]    Start read-only XJSON semantic bindings for XSL/UI clients
  Services                                    Show Micronaut services started by this host
  StopService -ServiceName <controller|research|static-site|phase-runtime-api|xsl-runtime-api>
  Worker -Task <Bot|Distill|Attention|Package|Validate|FelVerify|FelReplay|MetaFold> -WorkerId <id> ...

Examples:
  .\Micronaut.ps1 Host -Backend ollama
  .\Micronaut.ps1 Bot -Prompt "Explain this candidate neighborhood"
  .\Micronaut.ps1 Chat -AgentId daemon-bot
  .\Micronaut.ps1 AgentCreate -AgentId garden-guide -AgentName "Garden Guide"
  .\Micronaut.ps1 MicronautList
  .\Micronaut.ps1 MicronautInspect -EntryPath micronaut-coder.native.json
  .\Micronaut.ps1 NumpyTrain -InputPath micronaut\examples\numpy_gpt_training.txt -TrainingEpochs 5 -CheckpointPath .micronaut\checkpoints\char-gpt.safetensors
  .\Micronaut.ps1 NumpyGenerate -CheckpointPath .micronaut\checkpoints\char-gpt.safetensors -PromptText 'the cat'
  .\Micronaut.ps1 NumpyGenerate -PromptText 'Hello GPT' -MaxNewTokens 10 -TopK 5
  .\Micronaut.ps1 RPCList
  .\Micronaut.ps1 RPCCall -RpcPort model-api -Entry chat-completions -InputPath request.json
  .\Micronaut.ps1 StaticHost -InputPath .\site -Port 8080
  .\Micronaut.ps1 Distill -Word python -Backend local
  .\Micronaut.ps1 Attention -Entry python -Backend ollama
  .\Micronaut.ps1 Attention -EmbeddingBackend ollama -EmbeddingModel embeddinggemma:latest
  .\Micronaut.ps1 Package -All
  .\Micronaut.ps1 Todo
  .\Micronaut.ps1 Advisor -TaskId MN-PI-001
  .\Micronaut.ps1 EditWorker -TaskId MN-PI-001
  .\Micronaut.ps1 EditWorker -TaskId MN-PI-001 -Apply
  .\Micronaut.ps1 Worker -Task Distill -Word python -WorkerId python-field
  .\Micronaut.ps1 Worker -Task Attention -Entry python -WorkerId python-field
  .\Micronaut.ps1 FelVerify -InputPath events.fel.jsonl -WriteSvg
  .\Micronaut.ps1 StartController
  .\Micronaut.ps1 StartPhaseRuntimeApi
  .\Micronaut.ps1 StartPhaseRuntimeApi -PhaseRuntimePort 6180
  .\Micronaut.ps1 Services

Bounded task-worker edits require a task files allowlist and default to proposal-only. -Apply enables
exact-anchor writes with backups. Task-worker model calls and outcomes produce FEL replay logs and SVG projections.
Worker tasks invoke only the repository's allowlisted Python scripts. Worker files
are confined to .micronaut\sandboxes\<WorkerId>. This is a process-level workspace
boundary, not an operating-system security sandbox. Results remain DATA_ONLY.

MetaFold input is JSONL with one row per increasing tick:
{"tick":1,"state_root_sha256":"<64 hex>","lane_roots":{},"extra":{}}
'@ | Write-Output
}

function Resolve-RepoPath([string]$PathValue) {
    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        throw 'A file path is required.'
    }
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        $resolved = [System.IO.Path]::GetFullPath($PathValue)
    }
    else {
        $resolved = [System.IO.Path]::GetFullPath((Join-Path $script:RepoRoot $PathValue))
    }
    $prefix = $script:RepoRoot.TrimEnd('\') + '\'
    if (-not $resolved.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path must stay inside the repository: $PathValue"
    }

    # Reject existing junction/symlink components so a workspace path cannot escape
    # the repository or a worker's dedicated directory through a reparse point.
    $relative = $resolved.Substring($prefix.Length)
    $current = $script:RepoRoot
    foreach ($component in $relative.Split('\')) {
        if ([string]::IsNullOrEmpty($component)) { continue }
        $current = Join-Path $current $component
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Reparse-point paths are not allowed: $current"
            }
        }
    }
    return $resolved
}

function Assert-WorkerPath([string]$PathValue, [string]$SandboxPath) {
    $resolved = Resolve-RepoPath $PathValue
    $sandboxPrefix = $SandboxPath.TrimEnd('\') + '\'
    if (-not $resolved.StartsWith($sandboxPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Worker file access must stay inside its sandbox: $PathValue"
    }
    return $resolved
}

function Get-Python {
    if ($null -eq $script:Python) {
        $command = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -eq $command) {
            $command = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        }
        if ($null -eq $command) { throw 'Python was not found on PATH.' }
        $script:Python = $command.Source
    }
    return $script:Python
}

function Invoke-PythonTool([string]$ToolName, [string[]]$Arguments, [string]$WorkingDirectory = '') {
    $allowed = @('distill.py', 'neighborhood_attention.py', 'neighborhood_to_kso.py', 'kso_validate.py', 'build_micronaut_bson.py', 'micronaut\bson_bundle.py', 'micronaut\verifier.py', 'micronaut\fel_svg_replay.py', 'micronaut\fel_meta_fold.py', 'micronaut\fold_orchestrator.py', 'micronaut\bots.py', 'micronaut\advisor.py', 'micronaut\worker.py', 'micronaut\numpy_gpt_adam.py')
    if ($allowed -notcontains $ToolName) { throw "Python tool is not allowlisted: $ToolName" }
    $relativeToolPath = if ($ToolName.StartsWith('micronaut\', [System.StringComparison]::OrdinalIgnoreCase)) { $ToolName } else { Join-Path 'tools' $ToolName }
    $toolPath = Resolve-RepoPath $relativeToolPath
    if (-not (Test-Path -LiteralPath $toolPath -PathType Leaf)) { throw "Python tool is missing: $toolPath" }
    $oldNoBytecode = $env:PYTHONDONTWRITEBYTECODE
    $env:PYTHONDONTWRITEBYTECODE = '1'
    try {
        $runDirectory = if ([string]::IsNullOrWhiteSpace($WorkingDirectory)) { $script:RepoRoot } else { Resolve-RepoPath $WorkingDirectory }
        Push-Location $runDirectory
        try {
            & (Get-Python) $toolPath @Arguments
            $exitCode = $LASTEXITCODE
        }
        finally {
            Pop-Location
        }
    }
    finally {
        if ($null -eq $oldNoBytecode) { Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue }
        else { $env:PYTHONDONTWRITEBYTECODE = $oldNoBytecode }
    }
    if ($exitCode -ne 0) { throw "$ToolName exited with code $exitCode." }
}

function Get-EffectiveBackend([string]$ForAction) {
    if (-not [string]::IsNullOrWhiteSpace($Backend)) { return $Backend }
    if ($ForAction -in @('Attention', 'Bot', 'Host', 'Models')) { return 'ollama' }
    return 'local'
}

function Get-EffectiveModel([string]$ForAction, [string]$ForBackend) {
    if (-not [string]::IsNullOrWhiteSpace($Model)) { return $Model }
    if ($ForAction -eq 'Attention') {
        if ($ForBackend -eq 'ollama') { return $script:DefaultEmbeddingModel }
        if ($ForBackend -eq 'lmstudio') { return $script:DefaultEmbeddingModelLmStudio }
        throw 'Attention requires an embedding-capable Ollama or LM Studio model.'
    }
    if ($ForBackend -eq 'local') { return $script:DefaultLocalModel }
    if ($ForBackend -eq 'ollama') { return $script:DefaultOllamaModel }
    return $script:DefaultLmStudioModel
}

function Get-EffectiveEndpoint([string]$ForBackend, [string]$ForAction) {
    if (-not [string]::IsNullOrWhiteSpace($Endpoint)) {
        $value = $Endpoint.TrimEnd('/')
    }
    elseif ($ForBackend -eq 'ollama') {
        $value = if ($env:OLLAMA_HOST) { $env:OLLAMA_HOST.TrimEnd('/') } else { 'http://127.0.0.1:11434' }
    }
    elseif ($ForBackend -eq 'lmstudio') {
        $value = 'http://127.0.0.1:17889'
    }
    else {
        return $null
    }
    if ($ForAction -eq 'Attention' -and $ForBackend -eq 'lmstudio' -and -not $value.EndsWith('/v1')) {
        $value += '/v1'
    }
    return $value
}

function Invoke-HttpJson([string]$Uri, [string]$Method = 'GET', [object]$Body = $null) {
    $headers = @{}
    if ($env:LM_API_TOKEN) { $headers.Authorization = "Bearer $env:LM_API_TOKEN" }
    $params = @{ Uri = $Uri; Method = $Method; TimeoutSec = 5; ErrorAction = 'Stop' }
    if ($headers.Count -gt 0) { $params.Headers = $headers }
    if ($null -ne $Body) {
        $params.ContentType = 'application/json'
        $params.Body = $Body | ConvertTo-Json -Depth 12 -Compress
    }
    return Invoke-RestMethod @params
}

function Ensure-ModelHost([string]$ForBackend, [string]$ForModel, [string]$BaseEndpoint) {
    if ($ForBackend -eq 'local') {
        $modelPath = Resolve-Path -LiteralPath $ForModel -ErrorAction SilentlyContinue
        if ($null -eq $modelPath) { throw "Local GGUF model file not found: $ForModel" }
        Write-Output "Local model file is available: $($modelPath.Path)"
        return
    }
    if ($ForBackend -eq 'ollama') {
        try {
            $null = Invoke-HttpJson ($BaseEndpoint + '/api/tags')
        }
        catch {
            $ollama = Get-Command ollama.exe -CommandType Application -ErrorAction SilentlyContinue
            if ($null -eq $ollama) { $ollama = Get-Command ollama -CommandType Application -ErrorAction SilentlyContinue }
            if ($null -eq $ollama) { throw "Ollama is not reachable at $BaseEndpoint and ollama.exe was not found on PATH." }
            $logDirectory = Resolve-RepoPath '.micronaut\logs'
            New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
            $stdoutPath = Join-Path $logDirectory 'ollama-serve.out.log'
            $stderrPath = Join-Path $logDirectory 'ollama-serve.err.log'
            Start-Process -FilePath $ollama.Source -ArgumentList @('serve') -WorkingDirectory $script:RepoRoot `
                -WindowStyle Hidden -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath | Out-Null
            $ready = $false
            for ($attempt = 0; $attempt -lt 30; $attempt++) {
                Start-Sleep -Seconds 1
                try { $null = Invoke-HttpJson ($BaseEndpoint + '/api/tags'); $ready = $true; break }
                catch { }
            }
            if (-not $ready) { throw "Started Ollama but its API did not become ready at $BaseEndpoint. See $stderrPath" }
        }
        $tags = Invoke-HttpJson ($BaseEndpoint + '/api/tags')
        $available = @($tags.models | ForEach-Object { $_.name })
        if ($ForModel -and $available -notcontains $ForModel) {
            throw "Ollama is running, but model '$ForModel' is not installed. Install it with: ollama pull $ForModel"
        }
        Write-Output "Ollama model host ready at $BaseEndpoint; model: $ForModel"
        return
    }
    if ($ForBackend -eq 'lmstudio') {
        try { $null = Invoke-HttpJson ($BaseEndpoint + '/api/v1/models') }
        catch { throw "LM Studio API is not reachable at $BaseEndpoint. Start its local server and check LM_API_TOKEN if authentication is enabled." }
        Write-Output "LM Studio model host ready at $BaseEndpoint; requested model: $ForModel"
        return
    }
    throw "Unsupported model backend: $ForBackend"
}

function Show-Models([string]$ForBackend, [string]$BaseEndpoint) {
    if ($ForBackend -eq 'local') {
        $modelPath = Get-EffectiveModel 'Distill' 'local'
        if (Test-Path -LiteralPath $modelPath -PathType Leaf) { Write-Output "Local GGUF: $modelPath" }
        else { Write-Output "Local GGUF missing: $modelPath" }
        return
    }
    if ($ForBackend -eq 'ollama') {
        $tags = Invoke-HttpJson ($BaseEndpoint + '/api/tags')
        @($tags.models | ForEach-Object { $_.name }) | Write-Output
        return
    }
    $models = Invoke-HttpJson ($BaseEndpoint + '/api/v1/models')
    @($models.models | ForEach-Object { if ($_.name) { $_.name } elseif ($_.id) { $_.id } }) | Write-Output
}

function Get-ServiceManifestPath([string]$Name) {
    return Resolve-RepoPath (Join-Path '.micronaut\services' ($Name + '.json'))
}

function Start-MicronautService([string]$Name, [string]$ScriptRelative, [int]$Port, [string]$StaticRoot = $null) {
    $manifestPath = Get-ServiceManifestPath $Name
    if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
        try {
            $oldManifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
            $existing = Get-Process -Id ([int]$oldManifest.pid) -ErrorAction SilentlyContinue
            if ($null -ne $existing) {
                Write-Output "$Name service is already running (PID $($existing.Id), port $Port)."
                return
            }
        }
        catch { }
    }
    $scriptPath = Resolve-RepoPath $ScriptRelative
    $registry = Resolve-RepoPath $RegistryPath
    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) { throw "Micronaut service script is missing: $scriptPath" }
    if (-not (Test-Path -LiteralPath $registry -PathType Leaf)) { throw "Micronaut registry is missing: $registry" }
    $serviceDirectory = Resolve-RepoPath '.micronaut\services'
    New-Item -ItemType Directory -Path $serviceDirectory -Force | Out-Null
    $stdoutPath = Join-Path $serviceDirectory ($Name + '.out.log')
    $stderrPath = Join-Path $serviceDirectory ($Name + '.err.log')
    $pythonArgs = if ($Name -eq 'xsl-runtime-api') {
        @($scriptPath, '--host', '127.0.0.1', '--port', [string]$Port)
    } else {
        @($scriptPath, '--registry', $registry, '--host', '127.0.0.1', '--port', [string]$Port)
    }
    if ($Name -eq 'static-site') {
        if ([string]::IsNullOrWhiteSpace($StaticRoot) -or -not (Test-Path -LiteralPath $StaticRoot -PathType Container)) { throw 'StaticHost requires an existing site directory.' }
        $pythonArgs += @('--root', [System.IO.Path]::GetFullPath($StaticRoot))
    }
    if ($PolicyPin) { $pythonArgs += @('--policy-pin', $PolicyPin) }
    if ($AbiPin) { $pythonArgs += @('--abi-pin', $AbiPin) }
    $quotedArgs = ($pythonArgs | ForEach-Object { '"' + ([string]$_).Replace('"', '\"') + '"' }) -join ' '
    $process = Start-Process -FilePath (Get-Python) -ArgumentList $quotedArgs `
        -WorkingDirectory (Split-Path -Parent $scriptPath) -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    Start-Sleep -Seconds 2
    $stillRunning = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
    if ($null -eq $stillRunning) {
        $tail = if (Test-Path -LiteralPath $stderrPath) { (Get-Content -LiteralPath $stderrPath -Tail 12) -join ' ' } else { 'no service log was produced' }
        throw "$Name service exited during startup: $tail"
    }
    $manifest = [ordered]@{
        schema = 'kuhul.micronaut.service.v1'
        name = $Name
        script = $ScriptRelative
        pid = $process.Id
        processStartTime = $process.StartTime.ToUniversalTime().ToString('o')
        processStartFileTimeUtc = $process.StartTime.ToUniversalTime().ToFileTimeUtc()
        executable = (Get-Python)
        host = '127.0.0.1'
        port = $Port
        protocol = if ($Name -in @('static-site', 'xsl-runtime-api')) { 'http' } else { 'ws' }
        registry = $registry
        status = 'RUNNING'
        authority = [ordered]@{ semantic = $false; verification = $false; xcfeAdmission = $false; execution = $false; commit = $false }
        stdout = $stdoutPath
        stderr = $stderrPath
    }
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    $scheme = if ($Name -in @('static-site', 'xsl-runtime-api')) { 'http' } else { 'ws' }
    Write-Output "$Name service started at ${scheme}://127.0.0.1:$Port (PID $($process.Id))."
    Write-Output "Service manifest: $manifestPath"
}

function Start-PhaseRuntimeApi([int]$ApiPort) {
    if ($ApiPort -lt 1 -or $ApiPort -gt 65535) { throw 'PhaseRuntimePort must be between 1 and 65535.' }
    $baseUrl = "http://127.0.0.1:$ApiPort"
    try {
        $health = Invoke-HttpJson ($baseUrl + '/health')
        if ($health.status -eq 'ok' -and $health.runtime -eq 'kuhul_phase_runtime') {
            [Environment]::SetEnvironmentVariable('MICRONAUT_PHASE_RUNTIME_API', $baseUrl, 'Process')
            Write-Output "Phase runtime REST API is already responding at $baseUrl."
            return
        }
    }
    catch { }

    $scriptPath = Resolve-RepoPath 'bin\rest_api.py'
    $runtimePath = Resolve-RepoPath 'bin\kuhul_phase_runtime.exe'
    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) { throw "Phase runtime REST API script is missing: $scriptPath" }
    if (-not (Test-Path -LiteralPath $runtimePath -PathType Leaf)) { throw "Phase runtime executable is missing: $runtimePath" }

    $name = 'phase-runtime-api'
    $manifestPath = Get-ServiceManifestPath $name
    $serviceDirectory = Resolve-RepoPath '.micronaut\services'
    New-Item -ItemType Directory -Path $serviceDirectory -Force | Out-Null
    $stdoutPath = Join-Path $serviceDirectory ($name + '.out.log')
    $stderrPath = Join-Path $serviceDirectory ($name + '.err.log')
    $pythonArgs = @($scriptPath, '--host', '127.0.0.1', '--port', [string]$ApiPort, '--exe', $runtimePath)
    $quotedArgs = ($pythonArgs | ForEach-Object { '"' + ([string]$_).Replace('"', '\"') + '"' }) -join ' '
    $python = Get-Python
    $process = Start-Process -FilePath $python -ArgumentList $quotedArgs `
        -WorkingDirectory $script:RepoRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    Start-Sleep -Seconds 2
    $stillRunning = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
    if ($null -eq $stillRunning) {
        $tail = if (Test-Path -LiteralPath $stderrPath) { (Get-Content -LiteralPath $stderrPath -Tail 12) -join ' ' } else { 'no service log was produced' }
        throw "Phase runtime REST API exited during startup: $tail"
    }
    try {
        $health = Invoke-HttpJson ($baseUrl + '/health')
        if ($health.status -ne 'ok' -or $health.runtime -ne 'kuhul_phase_runtime') {
            throw 'health response does not identify the phase runtime'
        }
    }
    catch {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        throw "Phase runtime REST API failed its health check: $($_.Exception.Message)"
    }
    $manifest = [ordered]@{
        schema = 'kuhul.micronaut.service.v1'
        name = $name
        script = 'bin\rest_api.py'
        pid = $process.Id
        processStartTime = $process.StartTime.ToUniversalTime().ToString('o')
        processStartFileTimeUtc = $process.StartTime.ToUniversalTime().ToFileTimeUtc()
        executable = $python
        runtimeExecutable = $runtimePath
        host = '127.0.0.1'
        port = $ApiPort
        protocol = 'http'
        status = 'RUNNING'
        authority = [ordered]@{ semantic = $false; verification = $false; xcfeAdmission = $false; execution = $false; commit = $false }
        stdout = $stdoutPath
        stderr = $stderrPath
    }
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    [Environment]::SetEnvironmentVariable('MICRONAUT_PHASE_RUNTIME_API', $baseUrl, 'Process')
    Write-Output "Phase runtime REST API started at $baseUrl (PID $($process.Id))."
    Write-Output "Service manifest: $manifestPath"
}

function Start-NodeOrchestrator {
    $manifestPath = Get-ServiceManifestPath 'orchestrator'
    # The manifest can outlive its process or refer to a previous PID. Probe the
    # established loopback API before starting another server against the same store.
    try {
        $liveManifest = Invoke-HttpJson 'http://127.0.0.1:61683/api/manifest'
        if ($null -ne $liveManifest) {
            Write-Output 'orchestrator service is already responding at http://127.0.0.1:61683.'
            return
        }
    }
    catch { }

    if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
        try {
            $oldManifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
            $existing = Get-Process -Id ([int]$oldManifest.pid) -ErrorAction SilentlyContinue
            if ($null -ne $existing -and $oldManifest.processStartFileTimeUtc -eq $existing.StartTime.ToUniversalTime().ToFileTimeUtc()) {
                $null = Invoke-HttpJson 'http://127.0.0.1:61683/api/manifest'
                Write-Output "orchestrator service is already running (PID $($existing.Id), port 61683)."
                return
            }
        }
        catch { }
    }
    $node = Get-Command node.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($null -eq $node) { $node = Get-Command node -CommandType Application -ErrorAction SilentlyContinue }
    if ($null -eq $node) { throw 'Node.js was not found on PATH; it is required for the Daemon Bot XAIML API.' }
    $entryPoint = Resolve-RepoPath 'orchestrator.js'
    $serviceDirectory = Resolve-RepoPath '.micronaut\services'
    New-Item -ItemType Directory -Path $serviceDirectory -Force | Out-Null
    $stdoutPath = Join-Path $serviceDirectory 'orchestrator.out.log'
    $stderrPath = Join-Path $serviceDirectory 'orchestrator.err.log'
    $oldValues = @{ PORT = $env:PORT; OLLAMA_URL = $env:OLLAMA_URL; DEFAULT_MODEL = $env:DEFAULT_MODEL }
    try {
        $env:PORT = '61683'
        if (-not $env:OLLAMA_URL) { $env:OLLAMA_URL = 'http://127.0.0.1:11434' }
        if (-not $env:DEFAULT_MODEL) { $env:DEFAULT_MODEL = $script:DefaultOllamaModel }
        $process = Start-Process -FilePath $node.Source -ArgumentList ('"' + $entryPoint + '"') `
            -WorkingDirectory $script:RepoRoot -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    }
    finally {
        foreach ($name in @('PORT', 'OLLAMA_URL', 'DEFAULT_MODEL')) {
            $oldValue = $oldValues[$name]
            if ($null -eq $oldValue) { [Environment]::SetEnvironmentVariable($name, $null, 'Process') }
            else { [Environment]::SetEnvironmentVariable($name, $oldValue, 'Process') }
        }
    }
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        try { $null = Invoke-HttpJson 'http://127.0.0.1:61683/api/manifest'; $ready = $true; break }
        catch { }
        if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) { break }
    }
    if (-not $ready) {
        $tail = if (Test-Path -LiteralPath $stderrPath) { (Get-Content -LiteralPath $stderrPath -Tail 15) -join ' ' } else { 'no server log was produced' }
        throw "orchestrator did not become ready on localhost:61683: $tail"
    }
    $process.Refresh()
    $serviceManifest = [ordered]@{
        schema = 'kuhul.micronaut.service.v1'; name = 'orchestrator'; script = 'orchestrator.js'
        pid = $process.Id; processStartTime = $process.StartTime.ToUniversalTime().ToString('o')
        processStartFileTimeUtc = $process.StartTime.ToUniversalTime().ToFileTimeUtc()
        executable = $node.Source; host = '127.0.0.1'; port = 61683; status = 'RUNNING'
        authority = [ordered]@{ semantic = $false; verification = $false; xcfeAdmission = $false; execution = $false; commit = $false }
        stdout = $stdoutPath; stderr = $stderrPath
    }
    $serviceManifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
    Write-Output "orchestrator service started at http://127.0.0.1:61683 (PID $($process.Id))."
}

function Show-Services {
    $directory = Resolve-RepoPath '.micronaut\services'
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) { Write-Output 'No Micronaut services have been started.'; return }
    $manifests = @(Get-ChildItem -LiteralPath $directory -Filter '*.json' -File)
    if ($manifests.Count -eq 0) { Write-Output 'No Micronaut services have been started.'; return }
    foreach ($file in $manifests) {
        try {
            $manifest = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
            $process = Get-Process -Id ([int]$manifest.pid) -ErrorAction SilentlyContinue
            $status = if ($null -ne $process) { 'RUNNING' } else { 'STOPPED' }
            $protocol = if ($manifest.protocol) { [string]$manifest.protocol } elseif ($manifest.name -eq 'orchestrator') { 'http' } else { 'ws' }
            Write-Output ("{0}: {1} {2}://{3}:{4} PID={5}" -f $manifest.name, $status, $protocol, $manifest.host, $manifest.port, $manifest.pid)
        }
        catch { Write-Output ("{0}: invalid service manifest ({1})" -f $file.Name, $_.Exception.Message) }
    }
}

function Stop-MicronautService([string]$Name) {
    $manifestPath = Get-ServiceManifestPath $Name
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "No service manifest for '$Name'." }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $process = Get-Process -Id ([int]$manifest.pid) -ErrorAction SilentlyContinue
    if ($null -eq $process) { Write-Output "$Name service is already stopped."; return }
    $expectedPython = [System.IO.Path]::GetFullPath($(if ($manifest.executable) { $manifest.executable } else { Get-Python }))
    $actualPath = $process.Path
    if ($actualPath -and -not $actualPath.Equals($expectedPython, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "PID $($process.Id) no longer belongs to the recorded Python runtime; refusing to stop it."
    }
    if ($manifest.processStartFileTimeUtc -and [int64]$manifest.processStartFileTimeUtc -ne $process.StartTime.ToUniversalTime().ToFileTimeUtc()) {
        throw "PID $($process.Id) has been reused; refusing to stop it."
    }
    Stop-Process -Id $process.Id -Force
    Write-Output "$Name service stopped (PID $($process.Id))."
}

function Invoke-DaemonBot([string]$SandboxPath) {
    if ([string]::IsNullOrWhiteSpace($Prompt)) { throw 'Bot requires -Prompt.' }
    $backendValue = Get-EffectiveBackend 'Bot'
    if ($backendValue -eq 'local') { throw 'Daemon Bot requires the Ollama or LM Studio OpenAI-compatible endpoint.' }
    $modelValue = Get-EffectiveModel 'Distill' $backendValue
    $baseEndpoint = Get-EffectiveEndpoint $backendValue 'Distill'
    Ensure-ModelHost $backendValue $modelValue $baseEndpoint
    $apiBase = if ($baseEndpoint.EndsWith('/v1')) { $baseEndpoint } else { $baseEndpoint + '/v1' }

    if ($SandboxPath) {
        $responsePath = Assert-WorkerPath (Join-Path $SandboxPath 'response.txt') $SandboxPath
        $tracePath = Assert-WorkerPath (Join-Path $SandboxPath 'DAEMON-BOT_trace.jsonl') $SandboxPath
    }
    else {
        $logDirectory = Resolve-RepoPath '.micronaut\logs'
        New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
        $responsePath = if ($OutputPath) { Resolve-RepoPath $OutputPath } else { Join-Path $logDirectory 'daemon-bot-response.txt' }
        $tracePath = Join-Path $logDirectory 'DAEMON-BOT_trace.jsonl'
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $responsePath) -Force | Out-Null
    New-Item -ItemType Directory -Path (Split-Path -Parent $tracePath) -Force | Out-Null

    $environmentNames = @('MICRONAUT_API_BASE', 'MICRONAUT_API_KEY', 'MICRONAUT_MODEL', 'MICRONAUT_TRACE_PATH', 'MICRONAUT_RESULT_PATH')
    $previousEnvironment = @{}
    foreach ($name in $environmentNames) { $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
    try {
        $env:MICRONAUT_API_BASE = $apiBase
        $env:MICRONAUT_API_KEY = if ($backendValue -eq 'lmstudio' -and $env:LM_API_TOKEN) { $env:LM_API_TOKEN } else { 'ollama' }
        $env:MICRONAUT_MODEL = $modelValue
        $env:MICRONAUT_TRACE_PATH = $tracePath
        $env:MICRONAUT_RESULT_PATH = $responsePath
        Invoke-PythonTool 'micronaut\bots.py' @($Prompt)
        Write-Output "Daemon Bot response: $responsePath"
    }
    finally {
        foreach ($name in $environmentNames) {
            $oldValue = $previousEnvironment[$name]
            if ($null -eq $oldValue) { [Environment]::SetEnvironmentVariable($name, $null, 'Process') }
            else { [Environment]::SetEnvironmentVariable($name, $oldValue, 'Process') }
        }
    }
}

function New-UserDaemonAgent {
    if ([string]::IsNullOrWhiteSpace($AgentId) -or $AgentId -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$') {
        throw 'AgentCreate requires -AgentId with 1-48 letters, digits, underscores, or hyphens; the first character must be alphanumeric.'
    }
    if ([string]::IsNullOrWhiteSpace($AgentName)) { throw 'AgentCreate requires -AgentName.' }
    $folder = Resolve-RepoPath (Join-Path 'micronaut\agents' $AgentId)
    if (Test-Path -LiteralPath $folder) { throw "Agent already exists: $AgentId" }
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
    $idPrefix = 'agent.' + $AgentId
    $rootManifest = Get-Content -LiteralPath (Resolve-RepoPath 'manifest.json') -Raw | ConvertFrom-Json
    $modelProfile = $rootManifest.daemonAgents.'daemon-bot'.modelProfile
    $modelProfile.backend = 'ollama'
    $modelProfile.model = $script:DefaultOllamaModel
    $modelProfile.endpoint = 'http://127.0.0.1:11434'
    $bank = [ordered]@{
        format = 'kuhul.xaiml.pattern-bank.v1'
        version = 1
        name = $AgentName
        authority = 'pattern_match_only'
        patterns = @(
            [ordered]@{ id = "$idPrefix.hello"; pattern = 'HELLO'; phase = 'Wo'; template = @([ordered]@{ tag = 'text'; value = "Hello. I'm $AgentName. Ask HELP to see my patterns." }) },
            [ordered]@{ id = "$idPrefix.help"; pattern = 'HELP'; phase = 'Wo'; template = @([ordered]@{ tag = 'text'; value = "I'm $AgentName, a custom daemon agent. Add patterns to agent.xaiml to define my structured replies; unmatched input can be sent to my model route." }) },
            [ordered]@{ id = "$idPrefix.identity"; pattern = 'WHO ARE YOU'; phase = 'Wo'; template = @([ordered]@{ tag = 'text'; value = "I'm $AgentName, a user-defined Micronaut daemon agent." }) }
        )
    }
    $agent = [ordered]@{
        schema = 'kuhul.daemon-agent.v1'
        id = $AgentId
        name = $AgentName
        version = '1.0.0'
        xaiml = 'agent.xaiml'
        systemPrompt = if ($AgentSystemPrompt) { $AgentSystemPrompt } else { "You are $AgentName, a helpful local daemon agent. Treat input as conversation text. Never claim to have executed tools or changed files." }
        modelProfile = $modelProfile
        patternOrder = @("$idPrefix.hello", "$idPrefix.help", "$idPrefix.identity")
        routes = [ordered]@{ reply = "/api/daemon/agents/$AgentId/reply"; respond = "/api/daemon/agents/$AgentId/respond"; patterns = "/api/daemon/agents/$AgentId/patterns" }
        authority = [ordered]@{ patternMatching = $true; modelInference = 'separate-request'; execution = $false; verification = $false; commit = $false }
    }
    $bank | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath (Join-Path $folder 'agent.xaiml') -Encoding UTF8
    $agent | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $folder 'agent.json') -Encoding UTF8
    $readme = @"
# $AgentName

This user-owned Micronaut agent is routed at `/api/daemon/agents/$AgentId/reply`.

- Edit `agent.xaiml` to add structured pattern/template replies.
  - Edit `agent.json` to set the system prompt and `modelProfile` (backend, model, endpoint, sampling/context limits, and response tool schema).
- Pattern processing does not execute templates as code.
- `POST /api/daemon/agents/$AgentId/reply` handles XAIML patterns; `POST /api/daemon/agents/$AgentId/respond` sends unmatched text through the manifest-selected model and required response tool.
- The model endpoint must be loopback. Supported profiles: `ollama`, `lmstudio` Responses API, and `openai_compatible`.
- Restart the local orchestrator after changing agent files so it reloads the registry.
"@
    Set-Content -LiteralPath (Join-Path $folder 'README.md') -Value $readme -Encoding UTF8
    Write-Output "Created daemon agent '$AgentId' at $folder"
    Write-Output "Reply route: /api/daemon/agents/$AgentId/reply"
    Write-Output 'Restart the orchestrator to load the new agent.'
}

function Show-DaemonAgents {
    $null = Invoke-HttpJson 'http://127.0.0.1:61683/api/manifest'
    $result = Invoke-HttpJson 'http://127.0.0.1:61683/api/daemon/agents'
    $result.agents | ForEach-Object {
        Write-Output ("{0} ({1}) — {2} patterns — {3}" -f $_.id, $_.name, $_.patternCount, $_.replyRoute)
    }
}

function Get-MicronautDataRoot {
    return Resolve-RepoPath 'vendor\key-grammar-kit\data\micronauts'
}

function Show-MicronautDefinitions {
    $root = Get-MicronautDataRoot
    $files = @(Get-ChildItem -LiteralPath $root -File -Recurse:$Recursive | Sort-Object FullName)
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($script:RepoRoot.Length + 1).Replace('\', '/')
        $kind = 'source'
        $id = ''
        $name = ''
        if ($file.Extension -eq '.json') {
            try {
                $data = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($data.schema) { $kind = [string]$data.schema }
                elseif ($data.'@kind') { $kind = [string]$data.'@kind' }
                elseif ($data.kind) { $kind = [string]$data.kind }
                if ($data.id) { $id = [string]$data.id }
                elseif ($data.'@id') { $id = [string]$data.'@id' }
                if ($data.name) { $name = [string]$data.name }
            }
            catch { $kind = 'invalid-json' }
        }
        Write-Output ("{0}`t{1}`t{2}`t{3}" -f $relative, $kind, $id, $name)
    }
}

function Show-MicronautDefinition([string]$RequestedPath) {
    if ([string]::IsNullOrWhiteSpace($RequestedPath)) { throw 'MicronautInspect requires -EntryPath relative to vendor/key-grammar-kit/data/micronauts.' }
    if ([System.IO.Path]::IsPathRooted($RequestedPath)) { throw 'EntryPath must be relative to the micronauts data directory.' }
    $root = Get-MicronautDataRoot
    $candidate = Resolve-RepoPath (Join-Path 'vendor\key-grammar-kit\data\micronauts' $RequestedPath)
    $prefix = $root.TrimEnd('\') + '\'
    if (-not $candidate.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'EntryPath must stay inside vendor/key-grammar-kit/data/micronauts.' }
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "Micronaut definition not found: $RequestedPath" }
    $item = Get-Item -LiteralPath $candidate
    if ($item.Extension -eq '.json') {
        $data = Get-Content -LiteralPath $candidate -Raw -Encoding UTF8 | ConvertFrom-Json
        $data | ConvertTo-Json -Depth 50
    }
    else {
        Get-Content -LiteralPath $candidate -Raw -Encoding UTF8
    }
}

function Invoke-TaskAssistant([string]$Mode) {
    if ($Backend -eq 'local') {
        throw 'Task advisor/worker tool calls require Ollama or LM Studio. Load the GGUF in LM Studio and use -Backend lmstudio.'
    }
    $tool = if ($Mode -eq 'EditWorker') { 'micronaut\worker.py' } else { 'micronaut\advisor.py' }
    $pythonArgs = @()
    if ($Mode -eq 'Todo') { $pythonArgs += '--list' }
    if ($TaskId) { $pythonArgs += @('--task-id', $TaskId) }
    if ($Mode -eq 'Advisor' -and $Prompt) { $pythonArgs += @('--query', $Prompt) }
    if ($Mode -eq 'EditWorker' -and [string]::IsNullOrWhiteSpace($TaskId)) {
        throw 'EditWorker requires -TaskId from todo.md.'
    }
    if ($Backend) { $pythonArgs += @('--backend', $Backend) }
    if ($Model) { $pythonArgs += @('--model', $Model) }
    if ($Endpoint) { $pythonArgs += @('--endpoint', $Endpoint) }
    if ($Mode -eq 'EditWorker' -and $Apply) { $pythonArgs += '--apply' }
    Invoke-PythonTool $tool $pythonArgs
}

function Invoke-Action([string]$ForAction, [string]$ForTask, [string]$SandboxPath = $null) {
    $isWorker = -not [string]::IsNullOrWhiteSpace($SandboxPath)
    if ($isWorker) { New-Item -ItemType Directory -Path $SandboxPath -Force | Out-Null }
    switch ($ForTask) {
        'Bot' { Invoke-DaemonBot $SandboxPath }
        'Distill' {
            if ([string]::IsNullOrWhiteSpace($Word)) { throw 'Distill requires -Word.' }
            $backendValue = Get-EffectiveBackend 'Distill'
            $modelValue = Get-EffectiveModel 'Distill' $backendValue
            $endpointValue = Get-EffectiveEndpoint $backendValue 'Distill'
            Ensure-ModelHost $backendValue $modelValue $endpointValue
            $dest = if ($isWorker) { Join-Path $SandboxPath 'neighborhood.jsonl' } elseif ($OutputPath) { Resolve-RepoPath $OutputPath } else { Resolve-RepoPath 'neighborhood.jsonl' }
            if ($isWorker) { $dest = Assert-WorkerPath $dest $SandboxPath }
            $pythonArgs = @($Word, '--backend', $backendValue, '--model', $modelValue, '--output', $dest)
            if ($Context) { $pythonArgs += @('--context', $Context) }
            if ($endpointValue) { $pythonArgs += @('--endpoint', $endpointValue) }
            $pythonArgs += @('--duration-minutes', [string]$DurationMinutes, '--max-depth', [string]$MaxDepth, '--max-nodes', [string]$MaxNodes)
            if ($Recursive) { $pythonArgs += '--recursive' }
            Invoke-PythonTool 'distill.py' $pythonArgs
            if ($WithAttention -and (Test-Path -LiteralPath $dest -PathType Leaf)) {
                $previousEntry = $Entry
                $Entry = $Word
                try { Invoke-Action 'Worker' 'Attention' $SandboxPath }
                finally { $Entry = $previousEntry }
            }
        }
        'Attention' {
            $backendValue = if ($EmbeddingBackend) { $EmbeddingBackend } elseif ($Backend -and $Backend -ne 'local') { $Backend } else { 'ollama' }
            $modelValue = if ($EmbeddingModel) { $EmbeddingModel } else { Get-EffectiveModel 'Attention' $backendValue }
            $endpointValue = Get-EffectiveEndpoint $backendValue 'Attention'
            Ensure-ModelHost $backendValue $modelValue (Get-EffectiveEndpoint $backendValue 'Distill')
            $source = if ($isWorker) { Join-Path $SandboxPath 'neighborhood.jsonl' } elseif ($InputPath) { Resolve-RepoPath $InputPath } else { Resolve-RepoPath 'neighborhood.jsonl' }
            if ($isWorker) { $source = Assert-WorkerPath $source $SandboxPath }
            $dest = if ($isWorker) { Join-Path $SandboxPath 'neighborhood.attention.jsonl' } elseif ($OutputPath) { Resolve-RepoPath $OutputPath } else { Resolve-RepoPath 'neighborhood.attention.jsonl' }
            if ($isWorker) { $dest = Assert-WorkerPath $dest $SandboxPath }
            $pythonArgs = @('--input', $source, '--output', $dest, '--backend', $backendValue, '--model', $modelValue, '--endpoint', $endpointValue, '--temperature', [string]$AttentionTemperature)
            if ($Entry) { $pythonArgs += @('--entry', $Entry) }
            Invoke-PythonTool 'neighborhood_attention.py' $pythonArgs
        }
        'Package' {
            if ([string]::IsNullOrWhiteSpace($Entry) -and -not $All) { throw 'Package requires -Entry or -All.' }
            $source = if ($isWorker) { Join-Path $SandboxPath 'neighborhood.jsonl' } elseif ($InputPath) { Resolve-RepoPath $InputPath } else { Resolve-RepoPath 'neighborhood.jsonl' }
            if ($isWorker) { $source = Assert-WorkerPath $source $SandboxPath }
            $dest = if ($isWorker) { Join-Path $SandboxPath 'field.kso' } elseif ($OutputPath) { Resolve-RepoPath $OutputPath } else { Resolve-RepoPath 'field.kso' }
            if ($isWorker) { $dest = Assert-WorkerPath $dest $SandboxPath }
            $packageArgs = @('--input', $source, '--output', $dest)
            if ($All) { $packageArgs += @('--all', '--attention', 'neighborhood.attention.jsonl') }
            else { $packageArgs += @('--entry', $Entry) }
            Invoke-PythonTool 'neighborhood_to_kso.py' $packageArgs
        }
        'Validate' {
            $source = if ($isWorker) { if ($InputPath) { Join-Path $SandboxPath $InputPath } else { Join-Path $SandboxPath 'field.kso' } } elseif ($InputPath) { Resolve-RepoPath $InputPath } else { throw 'Validate requires -InputPath.' }
            if ($isWorker) { $source = Assert-WorkerPath $source $SandboxPath }
            Invoke-PythonTool 'kso_validate.py' @($source)
        }
        { $_ -in @('FelVerify', 'FelReplay') } {
            $source = if ($isWorker) { if ($InputPath) { Join-Path $SandboxPath $InputPath } else { Join-Path $SandboxPath 'events.fel.jsonl' } } elseif ($InputPath) { Resolve-RepoPath $InputPath } else { throw "$ForTask requires -InputPath." }
            if ($isWorker) { $source = Assert-WorkerPath $source $SandboxPath }
            $destination = if ($isWorker) { Join-Path $SandboxPath 'fel-output' } elseif ($OutputPath) { Resolve-RepoPath $OutputPath } else { Resolve-RepoPath '.micronaut\fel-output' }
            if ($isWorker) { $destination = Assert-WorkerPath $destination $SandboxPath }
            New-Item -ItemType Directory -Path $destination -Force | Out-Null
            if ($ForTask -eq 'FelReplay') {
                Invoke-PythonTool 'micronaut\fel_svg_replay.py' @($source, $destination)
            }
            else {
                $pythonArgs = @($source, '--out', $destination, '--registry', (Resolve-RepoPath $RegistryPath))
                if ($WriteSvg) { $pythonArgs += '--write-svg' }
                if ($WriteBin) { $pythonArgs += '--write-bin' }
                if ($Meta) { $pythonArgs += '--meta' }
                if ($PolicyPin) { $pythonArgs += @('--policy', $PolicyPin) }
                if ($AbiPin) { $pythonArgs += @('--abi', $AbiPin) }
                if ($RegistryPolicyPin) { $pythonArgs += @('--registry-policy-pin', $RegistryPolicyPin) }
                if ($RegistryAbiPin) { $pythonArgs += @('--registry-abi-pin', $RegistryAbiPin) }
                Invoke-PythonTool 'micronaut\verifier.py' $pythonArgs
            }
        }
        'MetaFold' {
            if (-not $PolicyPin -or -not $AbiPin) { throw 'MetaFold requires -PolicyPin and -AbiPin SHA-256 values.' }
            $stream = if ($StreamId) { $StreamId } elseif ($Entry) { $Entry } else { throw 'MetaFold requires -StreamId (or -Entry).' }
            $source = if ($isWorker) {
                if ($InputPath) { Join-Path $SandboxPath $InputPath } else { Join-Path $SandboxPath 'meta-input.jsonl' }
            } elseif ($InputPath) { Resolve-RepoPath $InputPath } else { throw 'MetaFold requires -InputPath.' }
            if ($isWorker) { $source = Assert-WorkerPath $source $SandboxPath }
            $destination = if ($isWorker) { Join-Path $SandboxPath 'meta-attestations.jsonl' } elseif ($OutputPath) { Resolve-RepoPath $OutputPath } else { Resolve-RepoPath '.micronaut\meta-output\meta-attestations.jsonl' }
            if ($isWorker) { $destination = Assert-WorkerPath $destination $SandboxPath }
            Invoke-PythonTool 'micronaut\fel_meta_fold.py' @('--input', $source, '--output', $destination, '--stream-id', $stream, '--policy-hash', $PolicyPin, '--abi-hash', $AbiPin)
        }
        default { throw "Unsupported worker task: $ForTask" }
    }
}

try {
    if ($Action -eq 'Help') { Write-Usage; exit 0 }
    if ($Action -eq 'Bundle') {
        Invoke-PythonTool 'build_micronaut_bson.py' @()
        exit 0
    }
    if ($Action -eq 'RPCList') {
        $rpcModule = Resolve-RepoPath 'bus\Micronaut.RpcBus.psm1'
        Import-Module $rpcModule -Force
        $rpcSource = if ($InputPath) { Resolve-RepoPath $InputPath } else { Resolve-RepoPath $RpcRegistryPath }
        Get-MicronautRpcPorts -Path $rpcSource | Format-Table -AutoSize
        exit 0
    }
    if ($Action -eq 'RPCCall') {
        if ([string]::IsNullOrWhiteSpace($RpcPort) -or [string]::IsNullOrWhiteSpace($Entry)) { throw 'RPCCall requires -RpcPort and -Entry (route id).' }
        if ($RpcPort -eq 'xsl-runtime-api' -and -not [Environment]::GetEnvironmentVariable('MICRONAUT_XSL_RUNTIME_API', 'Process')) {
            $serviceManifest = Get-ServiceManifestPath 'xsl-runtime-api'
            if (Test-Path -LiteralPath $serviceManifest -PathType Leaf) {
                $serviceInfo = Get-Content -LiteralPath $serviceManifest -Raw | ConvertFrom-Json
                if ($serviceInfo.host -eq '127.0.0.1' -and $serviceInfo.protocol -eq 'http') {
                    [Environment]::SetEnvironmentVariable('MICRONAUT_XSL_RUNTIME_API', "http://127.0.0.1:$([int]$serviceInfo.port)", 'Process')
                }
            }
        }
        $rpcModule = Resolve-RepoPath 'bus\Micronaut.RpcBus.psm1'
        Import-Module $rpcModule -Force
        $rpcSource = Resolve-RepoPath $RpcRegistryPath
        $payloadPath = if ($InputPath) { Resolve-RepoPath $InputPath } else { $null }
        Invoke-MicronautRpcRoute -Path $rpcSource -PortName $RpcPort -RouteName $Entry -PayloadPath $payloadPath | ConvertTo-Json -Depth 30
        exit 0
    }
    if ($Action -eq 'StaticHost') {
        if ([string]::IsNullOrWhiteSpace($InputPath)) { throw 'StaticHost requires -InputPath with the site directory.' }
        if ($Port -lt 1 -or $Port -gt 65535) { throw 'Port must be between 1 and 65535.' }
        $siteRoot = Resolve-RepoPath $InputPath
        if (-not (Test-Path -LiteralPath $siteRoot -PathType Container)) { throw "Static site directory not found: $siteRoot" }
        Start-MicronautService 'static-site' 'micronaut\static_site_server.py' $Port $siteRoot
        exit 0
    }
    if ($Action -in @('BundleList', 'BundleGet')) {
        $bundle = if ($InputPath) { Resolve-RepoPath $InputPath } else { Resolve-RepoPath 'micronaut.bson' }
        if ($Action -eq 'BundleGet' -and [string]::IsNullOrWhiteSpace($EntryPath)) { throw 'BundleGet requires -EntryPath.' }
        $bundleCommand = if ($Action -eq 'BundleList') { 'list' } else { 'get' }
        $bundleArgs = @((Resolve-RepoPath 'micronaut\bson_bundle.py'), $bundleCommand)
        if ($Action -eq 'BundleGet') { $bundleArgs += $EntryPath }
        $bundleArgs += @('--bundle', $bundle)
        & (Get-Python) @bundleArgs
        if ($LASTEXITCODE -ne 0) { throw "Micronaut BSON $bundleCommand failed with code $LASTEXITCODE." }
        exit 0
    }
    if ($Action -eq 'BundleRun') {
        if ([string]::IsNullOrWhiteSpace($EntryPath)) { throw 'BundleRun requires -EntryPath mu-py/<script.py>.' }
        $bundle = if ($InputPath) { Resolve-RepoPath $InputPath } else { Resolve-RepoPath 'micronaut.bson' }
        $runner = Resolve-RepoPath 'mu-py\micronaut_adapter.py'
        $runnerArgs = @($runner, '--micronaut.bson', $bundle, '--run-script', $EntryPath)
        if ($Execute) { $runnerArgs += '--execute' }
        if ($ScriptArgs.Count -gt 0) { $runnerArgs += '--'; $runnerArgs += $ScriptArgs }
        & (Get-Python) @runnerArgs
        if ($LASTEXITCODE -ne 0) { throw "Bundled program runner exited with code $LASTEXITCODE." }
        exit 0
    }
    if ($Action -eq 'Health') {
        $python = Get-Python
        & $python --version
        if ($LASTEXITCODE -ne 0) { throw 'Python health check failed.' }
        foreach ($backendValue in @('ollama', 'lmstudio')) {
            try {
                $base = Get-EffectiveEndpoint $backendValue 'Distill'
                $path = if ($backendValue -eq 'ollama') { '/api/tags' } else { '/api/v1/models' }
                $null = Invoke-HttpJson ($base + $path)
                Write-Output "${backendValue}: available at $base"
            }
            catch { Write-Output "${backendValue}: unavailable ($($_.Exception.Message))" }
        }
        exit 0
    }
    if ($Action -eq 'Models') {
        $backendValue = Get-EffectiveBackend 'Models'
        Show-Models $backendValue (Get-EffectiveEndpoint $backendValue 'Distill')
        exit 0
    }
    if ($Action -eq 'Host') {
        $backendValue = Get-EffectiveBackend 'Host'
        $modelValue = Get-EffectiveModel 'Distill' $backendValue
        Ensure-ModelHost $backendValue $modelValue (Get-EffectiveEndpoint $backendValue 'Distill')
        exit 0
    }
    if ($Action -eq 'Bot') { Invoke-DaemonBot $null; exit 0 }
    if ($Action -eq 'NumpyTrain') {
        if ($TrainingEpochs -le 0) { throw 'NumpyTrain requires TrainingEpochs greater than zero.' }
        if ($TrainingStride -le 0) { throw 'TrainingStride must be greater than zero.' }
        if ($LearningRate -le 0) { throw 'LearningRate must be greater than zero.' }
        if ($WeightDecay -lt 0) { throw 'WeightDecay cannot be negative.' }
        $trainingData = if ($InputPath) { Resolve-RepoPath $InputPath } else { Resolve-RepoPath 'micronaut\examples\numpy_gpt_training.txt' }
        if ($QueryHeads -le 0 -or $KVHeads -le 0 -or ($QueryHeads % $KVHeads) -ne 0 -or (32 % $QueryHeads) -ne 0) { throw 'QueryHeads must divide the model width (32), and KVHeads must evenly divide QueryHeads.' }
        $trainingArgs = @('--data', $trainingData, '--epochs', [string]$TrainingEpochs, '--stride', [string]$TrainingStride, '--max-seq-len', [string]$MaxSeqLen, '--learning-rate', [string]$LearningRate, '--weight-decay', [string]$WeightDecay, '--optimizer', $OptimizerBackend, '--num-heads', [string]$QueryHeads, '--num-kv-heads', [string]$KVHeads, '--seed', [string]$RandomSeed)
        if ($OpenCLDevice) { $trainingArgs += @('--opencl-device', $OpenCLDevice) }
        if ($CheckpointPath) { $trainingArgs += @('--save-safetensors', (Resolve-RepoPath $CheckpointPath)) }
        Invoke-PythonTool 'micronaut\numpy_gpt_adam.py' $trainingArgs
        exit 0
    }
    if ($Action -eq 'NumpyGenerate') {
        if ($MaxNewTokens -lt 0) { throw 'NumpyGenerate requires MaxNewTokens greater than or equal to zero.' }
        if ($MaxSeqLen -le 0) { throw 'MaxSeqLen must be greater than zero.' }
        if ($GenerationTemperature -lt 0) { throw 'GenerationTemperature cannot be negative; use 0 for greedy decoding.' }
        if ($TopK -lt 0) { throw 'TopK cannot be negative; use 0 to disable top-k filtering.' }
        $generationWidth = if ($PromptTokens.Count -gt 0) { 16 } else { 32 }
        if ($QueryHeads -le 0 -or $KVHeads -le 0 -or ($QueryHeads % $KVHeads) -ne 0 -or ($generationWidth % $QueryHeads) -ne 0) { throw "QueryHeads must divide model width $generationWidth, and KVHeads must evenly divide QueryHeads." }
        if ($PromptTokens.Count -gt 0) {
            $generateArgs = @('--generate-prompt') + @($PromptTokens | ForEach-Object { [string]$_ })
        }
        else {
            if ([string]::IsNullOrEmpty($PromptText)) { throw 'NumpyGenerate requires non-empty PromptText or PromptTokens.' }
            if ([string]::IsNullOrEmpty($CorpusText)) { throw 'CorpusText must not be empty.' }
            $generateArgs = @('--generate-text', $PromptText, '--corpus', $CorpusText, '--max-seq-len', [string]$MaxSeqLen)
        }
        $generateArgs += @('--max-new-tokens', [string]$MaxNewTokens, '--temperature', [string]$GenerationTemperature, '--num-heads', [string]$QueryHeads, '--num-kv-heads', [string]$KVHeads, '--seed', [string]$RandomSeed)
        if ($TopK -gt 0) { $generateArgs += @('--top-k', [string]$TopK) }
        if ($CheckpointPath) { $generateArgs += @('--load-safetensors', (Resolve-RepoPath $CheckpointPath)) }
        Invoke-PythonTool 'micronaut\numpy_gpt_adam.py' $generateArgs
        exit 0
    }
    if ($Action -in @('Todo', 'Advisor', 'EditWorker')) { Invoke-TaskAssistant $Action; exit 0 }
    if ($Action -eq 'AgentCreate') { New-UserDaemonAgent; exit 0 }
    if ($Action -eq 'AgentList') { Show-DaemonAgents; exit 0 }
    if ($Action -eq 'MicronautList') { Show-MicronautDefinitions; exit 0 }
    if ($Action -eq 'MicronautInspect') { Show-MicronautDefinition $EntryPath; exit 0 }
    if ($Action -eq 'StartOrchestrator') { Start-NodeOrchestrator; exit 0 }
    if ($Action -eq 'FoldDemo') {
        $demoDirectory = Resolve-RepoPath '.micronaut\fold-demo'
        New-Item -ItemType Directory -Path $demoDirectory -Force | Out-Null
        Invoke-PythonTool 'micronaut\fold_orchestrator.py' @() '.micronaut\fold-demo'
        exit 0
    }
    if ($Action -eq 'Chat') {
        if ([string]::IsNullOrWhiteSpace($AgentId)) { $AgentId = 'daemon-bot' }
        if ($AgentId -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$') { throw 'AgentId must contain 1-48 letters, digits, underscores, or hyphens.' }
        Start-NodeOrchestrator
        $python = Get-Python
        $cli = Resolve-RepoPath 'micronaut\daemon_cli.py'
        & $python $cli --agent-id $AgentId
        if ($LASTEXITCODE -ne 0) { throw "Daemon CLI exited with code $LASTEXITCODE." }
        exit 0
    }
    if ($Action -eq 'StartController') {
        Start-MicronautService 'controller' 'micronaut\ws_bot_controller.py' 8765
        exit 0
    }
    if ($Action -eq 'StartResearch') {
        Start-MicronautService 'research' 'micronaut\ws_research_bot.py' 8766
        exit 0
    }
    if ($Action -eq 'StartPhaseRuntimeApi') {
        Start-PhaseRuntimeApi $PhaseRuntimePort
        exit 0
    }
    if ($Action -eq 'StartXslRuntimeApi') {
        if ($XslRuntimePort -lt 1 -or $XslRuntimePort -gt 65535) { throw 'XslRuntimePort must be between 1 and 65535.' }
        [Environment]::SetEnvironmentVariable('MICRONAUT_XSL_RUNTIME_API', "http://127.0.0.1:$XslRuntimePort", 'Process')
        Start-MicronautService 'xsl-runtime-api' 'micronaut\xjson_api.py' $XslRuntimePort
        try {
            $health = Invoke-HttpJson ("http://127.0.0.1:$XslRuntimePort/health")
            if ($health.status -ne 'ok' -or $health.service -ne 'kuhul-xjson-bindings') { throw 'health response does not identify XJSON semantic bindings' }
        }
        catch { throw "XSL semantic bindings API failed its health check: $($_.Exception.Message)" }
        Write-Output "XSL semantic bindings are available at http://127.0.0.1:$XslRuntimePort/api/xsl/descriptor"
        exit 0
    }
    if ($Action -eq 'Services') { Show-Services; exit 0 }
    if ($Action -eq 'StopService') {
        if ([string]::IsNullOrWhiteSpace($ServiceName)) { throw 'StopService requires -ServiceName controller|research|static-site|phase-runtime-api|xsl-runtime-api.' }
        Stop-MicronautService $ServiceName
        exit 0
    }
    if ($Action -eq 'Worker') {
        if ([string]::IsNullOrWhiteSpace($Task)) { throw 'Worker requires -Task Distill|Attention|Package|Validate|FelVerify|FelReplay|MetaFold.' }
        if ([string]::IsNullOrWhiteSpace($WorkerId)) { $WorkerId = 'worker-' + (Get-Date -Format 'yyyyMMdd-HHmmss') }
        if ($WorkerId -notmatch '^[A-Za-z0-9_-]{1,48}$') { throw 'WorkerId must contain 1-48 letters, digits, underscores, or hyphens.' }
        $sandbox = Resolve-RepoPath (Join-Path '.micronaut\sandboxes' $WorkerId)
        New-Item -ItemType Directory -Path $sandbox -Force | Out-Null
        $manifestPath = Join-Path $sandbox 'worker.json'
        $manifest = [ordered]@{
            schema = 'kuhul.micronaut.worker.v1'
            workerId = $WorkerId
            task = $Task
            word = $Word
            backend = $Backend
            model = $Model
            status = 'RUNNING'
            startedAt = [DateTime]::UtcNow.ToString('o')
            sandbox = $sandbox
            allowedTools = @('distill.py', 'neighborhood_attention.py', 'neighborhood_to_kso.py', 'kso_validate.py', 'micronaut\verifier.py', 'micronaut\fel_svg_replay.py', 'micronaut\fel_meta_fold.py', 'micronaut\bots.py')
            micronautComponents = [ordered]@{
                bot = 'micronaut\bots.py'
                nativeBridge = 'micronaut\micronaut_native.py'
                cli = 'micronaut\cli_interface.py'
                daemonCli = 'micronaut\daemon_cli.py'
                orchestrator = 'micronaut\orchestrator_bot.py'
                foldOrchestrator = 'micronaut\fold_orchestrator.py'
                felVerifier = 'micronaut\verifier.py'
                felReplay = 'micronaut\fel_svg_replay.py'
                felMetaFold = 'micronaut\fel_meta_fold.py'
                websocketController = 'micronaut\ws_bot_controller.py'
                websocketResearch = 'micronaut\ws_research_bot.py'
                clusterOrchestrator = 'micronaut\safetensors_cluster_orchestrator.py'
            }
            admission = 'DATA_ONLY'
            authority = [ordered]@{ semantic = $false; verification = $false; xcfeAdmission = $false; execution = $false; commit = $false }
        }
        try {
            Invoke-Action 'Worker' $Task $sandbox
            $manifest.status = 'COMPLETED_DATA_ONLY'
            $manifest.completedAt = [DateTime]::UtcNow.ToString('o')
        }
        catch {
            $manifest.status = 'FAILED'
            $manifest.error = $_.Exception.Message
            $manifest.completedAt = [DateTime]::UtcNow.ToString('o')
            throw
        }
        finally {
            $manifest | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
        }
        Write-Output "Worker sandbox: $sandbox"
        Write-Output "Worker manifest: $manifestPath"
        exit 0
    }
    Invoke-Action $Action $Action
    exit 0
}
catch {
    $errorRecord = $_
    $location = if ($errorRecord.InvocationInfo -and $errorRecord.InvocationInfo.ScriptLineNumber -gt 0) {
        " at Micronaut.ps1:$($errorRecord.InvocationInfo.ScriptLineNumber)"
    } else { '' }
    [Console]::Error.WriteLine("Micronaut failed$location`: $($errorRecord.Exception.Message)")
    if ($errorRecord.ScriptStackTrace) { [Console]::Error.WriteLine($errorRecord.ScriptStackTrace) }
    exit 1
}
