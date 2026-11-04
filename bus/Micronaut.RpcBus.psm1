Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-MicronautRpcRegistry {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)

    $resolved = [System.IO.Path]::GetFullPath($Path)
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) { throw "RPC registry or BSON bundle not found: $resolved" }
    if ([System.IO.Path]::GetExtension($resolved) -eq '.bson') {
        $root = Split-Path -Parent $PSScriptRoot
        $reader = Join-Path $root 'micronaut\bson_bundle.py'
        $python = Get-Command python -CommandType Application -ErrorAction SilentlyContinue
        if ($null -eq $python) { throw 'Python is required to read rpcApi from micronaut.bson.' }
        $json = & $python.Source $reader rpc --bundle $resolved
        if ($LASTEXITCODE -ne 0) { throw 'Could not read RPC registry projection from BSON.' }
        $registry = ($json -join "`n") | ConvertFrom-Json
    }
    else {
        $registry = Get-Content -LiteralPath $resolved -Raw -Encoding UTF8 | ConvertFrom-Json
    }

    if ($registry.schema -ne 'kuhul.micronaut.rpc-api.v1' -or [int]$registry.version -ne 1 -or $null -eq $registry.ports) {
        throw 'RPC registry has an unsupported schema or is missing ports.'
    }
    foreach ($portProperty in $registry.ports.PSObject.Properties) {
        $port = $portProperty.Value
        if ($port.provider -notin @('rest-json', 'opencl-adamw', 'http-static', 'local-jsonl-fold', 'local-deterministic-classifier')) {
            throw "Port '$($portProperty.Name)' uses a provider not allowed by the host: '$($port.provider)'"
        }
        if ($port.provider -eq 'rest-json') {
            if ([string]::IsNullOrWhiteSpace([string]$port.endpointEnv) -or $null -eq $port.routes) { throw "REST port '$($portProperty.Name)' needs endpointEnv and routes." }
            foreach ($routeProperty in $port.routes.PSObject.Properties) {
                $route = $routeProperty.Value
                if ($route.method -notin @('GET', 'POST', 'PUT', 'PATCH', 'DELETE') -or [string]$route.path -notmatch '^/[A-Za-z0-9_./{}-]*$' -or [string]$route.path -match '\.\.') {
                    throw "REST route '$($routeProperty.Name)' on port '$($portProperty.Name)' has an invalid method or path."
                }
            }
        }
    }
    return $registry
}

function Get-MicronautRpcPorts {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path)
    $registry = Get-MicronautRpcRegistry -Path $Path
    foreach ($property in $registry.ports.PSObject.Properties) {
        $port = $property.Value
        $routes = @($port.routes.PSObject.Properties | ForEach-Object { $_.Name })
        $dispatch = if ($port.PSObject.Properties['dispatch']) { $port.dispatch } else { $null }
        [pscustomobject]@{
            name = $property.Name
            provider = $port.provider
            description = $port.description
            routes = $routes -join ', '
            dispatch = $dispatch
        }
    }
}

function Invoke-MicronautRpcRoute {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$PortName,
        [Parameter(Mandatory)][string]$RouteName,
        [string]$PayloadPath
    )
    $registry = Get-MicronautRpcRegistry -Path $Path
    $port = $registry.ports.$PortName
    if ($null -eq $port) { throw "Unknown RPC port '$PortName'. Use RPCList to discover ports." }
    if ($port.provider -ne 'rest-json') { throw "Port '$PortName' is host-dispatched via '$($port.dispatch)'; it is not a REST route." }
    $route = $port.routes.$RouteName
    if ($null -eq $route) { throw "Unknown route '$RouteName' on port '$PortName'." }
    $base = [Environment]::GetEnvironmentVariable([string]$port.endpointEnv, 'Process')
    if ([string]::IsNullOrWhiteSpace($base)) { throw "Set environment variable $($port.endpointEnv) to the API base URL first." }
    $uri = [Uri]::new($base.TrimEnd('/') + [string]$route.path)
    if ($uri.Scheme -ne 'https' -and -not ($uri.IsLoopback -and $uri.Scheme -eq 'http')) { throw 'RPC endpoint must use HTTPS, or HTTP on a loopback address.' }
    $headers = @{}
    $tokenEnv = if ($port.PSObject.Properties['tokenEnv']) { [string]$port.tokenEnv } else { '' }
    if ($tokenEnv) {
        $token = [Environment]::GetEnvironmentVariable($tokenEnv, 'Process')
        if ($token) { $headers.Authorization = "Bearer $token" }
    }
    $request = @{ Uri = $uri; Method = [string]$route.method; Headers = $headers; ErrorAction = 'Stop' }
    if ($route.method -in @('POST', 'PUT', 'PATCH')) {
        if (-not $PayloadPath) { throw "Route '$RouteName' requires -InputPath with a JSON request body." }
        $payload = [System.IO.Path]::GetFullPath($PayloadPath)
        if (-not (Test-Path -LiteralPath $payload -PathType Leaf)) { throw "RPC payload file not found: $payload" }
        $request.Body = Get-Content -LiteralPath $payload -Raw -Encoding UTF8
        $request.ContentType = 'application/json'
    }
    elseif ($route.method -eq 'GET' -and $PayloadPath) {
        $payloadFile = [System.IO.Path]::GetFullPath($PayloadPath)
        if (-not (Test-Path -LiteralPath $payloadFile -PathType Leaf)) { throw "RPC query file not found: $payloadFile" }
        $queryValues = Get-Content -LiteralPath $payloadFile -Raw -Encoding UTF8 | ConvertFrom-Json -AsHashtable
        if ($queryValues -isnot [System.Collections.IDictionary]) { throw 'GET query payload must be a JSON object of scalar values.' }
        $queryParts = @()
        foreach ($key in $queryValues.Keys) {
            $value = $queryValues[$key]
            if ($null -eq $value -or $value -is [System.Collections.IDictionary] -or $value -is [array]) {
                throw "GET query value '$key' must be a non-null scalar."
            }
            $queryParts += ([Uri]::EscapeDataString([string]$key) + '=' + [Uri]::EscapeDataString([string]$value))
        }
        $uriBuilder = [UriBuilder]::new($uri)
        $existingQuery = $uriBuilder.Query.TrimStart('?')
        $newQuery = $queryParts -join '&'
        $querySegments = @()
        if ($existingQuery) { $querySegments += $existingQuery }
        if ($newQuery) { $querySegments += $newQuery }
        $uriBuilder.Query = $querySegments -join '&'
        $request.Uri = $uriBuilder.Uri
    }
    Invoke-RestMethod @request
}

Export-ModuleMember -Function Get-MicronautRpcRegistry, Get-MicronautRpcPorts, Invoke-MicronautRpcRoute
