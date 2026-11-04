---
name: run-tests
description: Run the full K'UHUL test suite (all 4 required parts in order). Use when verifying a change is correct before marking it done.
---

Run all four test suites in order. All must pass.

## 1. Kit validation (16 track tests)

```batch
cd C:\public_html\kuhul
vendor\key-grammar-kit\test.bat
```

Expected: 16 track tests with 7 PASS checks.

## 2. Python unit tests (111 tests)

```bash
python -m unittest discover -s micronaut -t . -p "test_*.py" -q
```

Expected: 111 tests passing. One pre-existing glyph_buffer_engine import error may appear — this is a known issue when running via discovery and does not indicate a regression.

## 3. Standalone learning lane test

```bash
python flat\test_learning_lane_durable.py
```

Expected: 1 test passing.

## 4. Node.js tests

```bash
npm test
```

If any suite fails, report which suite failed, the error output, and what file/function is implicated. Do not mark a change complete until all four suites pass.
