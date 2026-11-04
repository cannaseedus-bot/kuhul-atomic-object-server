# KSO1 package contract

`.kso` is the BSON-encoded compiled K'UHUL symbolic object. `kso.schema.json` describes its Extended JSON inspection/authoring view; it does not encode BSON bytes. BSON binary subdocuments use canonical Extended JSON `$binary` values when shown as JSON.

## KSO1 binary framing (version 1)

The file is exactly one four-byte ASCII header followed by exactly one BSON document:

| Offset | Contents |
| --- | --- |
| 0–3 | `KSO1` (`4B 53 4F 31`) |
| 4 onward | One BSON document; its signed little-endian int32 length includes the length field and final NUL |

The BSON document must end exactly at EOF. V1 rejects a short header, incorrect header, BSON length below 5, a length over the configured package limit, truncated bytes, malformed BSON, duplicate critical keys, unsupported `version`, a missing or mismatched document `magic`, and any trailing bytes. The BSON envelope independently contains `magic: "KSO1"` and `version: 1`; both must agree with the header and supported loader version. The loader checks the declared size against the configured maximum before allocating the document buffer.

The package keeps semantic and recursive lane definitions lossless, either embedded or referenced. External references are the default so the source JSON schemas remain authoritative. A compiler may emit resolved typed bindings, but loading a package never grants XCFE admission or dispatch authority. A successful loader result is `DATA_ONLY`; host-controlled XCFE admission is a separate operation.

External references are resolved relative to the package location unless an explicit resolver policy supplies another base. Resolution must remain deterministic and report missing or invalid references. The lane registry preserves one canonical definition for shared glyphs such as `⟁GASOLINE`, with multiple incoming reference edges. Each recursive visit creates its own fold instance; cycle detection checks only the active traversal path, so a completed node may be revisited through another edge.

`.cso` remains a separate Direct3D shader bytecode resource. A KSO kernel may embed its bytes as BSON Binary or reference an external `.cso`; the package records backend, language, profile, format, entry point, and binding metadata. Shader backend capability checks belong to compilation/loading. HLSL compute kernels require a compatible Direct3D backend and are not assumed to run as WebGL2 shaders.

`.asxg` remains a distinct atomic execution-lane payload. KSO may refer to or carry it as an opaque binary payload; it does not reinterpret its contents.

The BSON document uses the `KSO1` magic and format/version fields shown in `kso.schema.json`. Implementations should impose a configurable package-size limit and chunk or externally reference large SCXQ2/vector payloads rather than assume an unbounded BSON document. The header is format identification only; it provides no integrity or authenticity guarantee. Any future hash or signature is a separately versioned contract. XCFE admission remains explicit, host-authorized, and separate from package parsing.

## Neighborhood attention sidecar

`python tools/neighborhood_attention.py --input neighborhood.jsonl --output neighborhood.attention.jsonl --model embeddinggemma:latest` embeds each record's identity, relation, and context questions against its neighbor glyphs. Existing `field.reasoningQuestions` take precedence. The resulting softmax weights are candidate relevance values only.

`python tools/neighborhood_to_kso.py --input neighborhood.jsonl --all --attention neighborhood.attention.jsonl --output field.kso` embeds the complete source JSONL in the KSO semantic definition. The `attention` envelope entry points to the typed JSONL vector pool, keeping BSON bounded while preserving per-question query, thought, relation, glyph, and fold keys. Attention scores use the full-precision model vectors; stored JSON vectors are rounded to six decimals. Repeated candidate snapshots remain in `semantic.data.records`; `byGlyph` stores zero-based record indexes instead of duplicating records in BSON.

The KSO1 validator checks that this relative attention payload exists beside the package and rejects paths that escape the package directory. The large JSONL remains external so the BSON document stays below the standard 16 MiB document limit.
