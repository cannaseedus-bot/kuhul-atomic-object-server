# K'UHUL Phase Runtime REST API

Start the local API from the repository root:

```powershell
py -3 bin/rest_api.py
```

The host-managed service can be started with
`Micronaut.ps1 StartPhaseRuntimeApi` or from the CommandBus catalog using
`phase-runtime-api-start`. The host sets `MICRONAUT_PHASE_RUNTIME_API` to the
active loopback URL in that PowerShell session. The RPC registry exposes the
`phase-runtime-api` port with `health`, `phases`, and `validate` routes; use
`Micronaut.ps1 RPCList` to inspect it and `Micronaut.ps1 RPCCall` to invoke a
route. Stop the managed service with
`Micronaut.ps1 StopService -ServiceName phase-runtime-api`.

The default address is `http://127.0.0.1:6170`. Override the runtime executable
with `--exe`, or choose a different bind address and port with `--host` and
`--port`.

## Endpoints

### `GET /health`

Returns runtime availability:

```json
{"status":"ok","runtime":"kuhul_phase_runtime"}
```

### `GET /phases`

Runs the executable and returns its phase transitions and operation
authorization as JSON.

### `POST /validate`

Validates one or more in-memory `.kbnf`, `.kgf`, or `.kl` files by passing
temporary files to the runtime executable:

```json
{
  "files": [
    {"name":"starter.kgf","content":"[example]\n"}
  ]
}
```

Response:

```json
{
  "status":"valid",
  "valid_count":1,
  "file_count":1,
  "files":[{"name":"starter.kgf","valid":true,"output":"starter.kgf: valid .kgf file"}]
}
```

Requests are limited to 1 MiB total, 256 KiB per file, and 16 files. The API
accepts filenames and content, not caller-supplied filesystem paths. It binds
to loopback by default.
