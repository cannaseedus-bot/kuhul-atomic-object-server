# Native K'UHUL phase runtime

The CLI supports phase-runtime inspection and a standalone XPath 3.1 expression evaluation entry point:

```powershell
kuhul_phase_runtime.exe --xpath 'for $x in 1 to 3 return $x * $x'
kuhul_phase_runtime.exe --xpath '/b:library/b:book' --context books.xml --namespace 'b=urn:books'
kuhul_phase_runtime.exe --xpath-file query.xpath --context books.xml
```

XPath 3.1 maps also work as ordinary semantic data. For example, this resolves a phase code through nested map lookup:

```powershell
kuhul_phase_runtime.exe --xpath 'let $phases := map { "Pop": map { "code": "000", "role": "Ingress", "operators": ["MAP"] }, "Yax": map { "code": "010", "role": "Expansion", "operators": ["MAP", "FILTER"] }, "Ch''en": map { "code": "100", "role": "Verification", "operators": ["FILTER", "REDUCE"] } } return $phases?Yax?code'
```

`$phases?Yax?code` returns the descriptor value `"010"`. A map constructor is a data structure; a value such as `"MAP"` in its `operators` array is descriptive data and does not invoke K'UHUL's `MAP` transformation operator or grant execution permission. The native evaluator returns map and array values as typed JSON while keeping `admission: not_evaluated`.

The same map semantics can hold a Micronaut binding:

```powershell
kuhul_phase_runtime.exe --xpath 'let $micronauts := map { "micronaut:ELIZA": map { "phase": "Yax", "capability": "question_proposal", "srai": "srai:DIAGNOSE_MEMORY", "gap": "cfpc:MEMORY_FAILURE_MECHANISM" } } return $micronauts("micronaut:ELIZA")?gap'
```

This returns the string `cfpc:MEMORY_FAILURE_MECHANISM`. Looking up `?srai` returns the SRAI reference as data; it does not invoke that redirect, call ELIZA, or pass an XCFE gate. A map can carry semantic references and metadata while admission remains a separate runtime decision.

XPath evaluation is delegated to SaxonC-HE through the adjacent `xpath_eval.py` adapter. Install `saxonche` from the repository's `requirements.txt`; set `KUHUL_PYTHON` if the Python executable is not named `python`. Results are returned as typed JSON containing XDM atomic, node, map, array, and function items. An optional XML file supplies the context node, and `--namespace prefix=uri` declares XPath namespace bindings.

The evaluator pins the language version to XPath 3.1 and disables external URI protocols for query-time functions such as `doc()` and `unparsed-text()`. An explicitly supplied context XML file is parsed as the query context. Evaluation results carry `admission: not_evaluated`; XPath evaluation does not make an operation eligible, admitted, or authorized. K'UHUL phase, Micronaut, AIML, and XCFE host forms remain runtime contracts around the expression language and are not executed by this expression-only command.
