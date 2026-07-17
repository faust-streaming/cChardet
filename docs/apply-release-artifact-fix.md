# Patch: fix dropped sdist / wheels in an `upload-artifact@v4` release workflow

A step-by-step patch you can apply to other projects that publish wheels + an
sdist from a GitHub Actions "build fan-out → single publish job" workflow.

It fixes the bug where a release ends up **missing its sdist** (and often some
platforms' wheels) even though the workflow run is **green** — caused by
`upload-artifact@v4` no longer merging same-named artifacts, plus a stale
publish action whose `skip-existing` can't skip.

> Background / why: see `fixing-dropped-sdist-in-release-workflows.md`.

---

## 1. Does this project need the patch?

Apply it if **all** of these are true of the release workflow:

- [ ] Two or more `actions/upload-artifact@v4` steps with **no `name:`** (or the
      **same** `name:`) — typically a wheels matrix + an sdist job.
- [ ] A `actions/download-artifact@v4` that selects by `name:` (one artifact)
      rather than `pattern:` + `merge-multiple: true`.
- [ ] `pypa/gh-action-pypi-publish` older than ~`v1.9` (e.g. `v1.5.0`).

Confirm the symptom on the index (optional):

```bash
curl -s https://pypi.org/pypi/<project>/<version>/json \
  | python3 -c 'import sys,json;u=json.load(sys.stdin)["urls"];
print("sdist:", any(x["packagetype"]=="sdist" for x in u),
      "| wheels:", sum(x["packagetype"]=="bdist_wheel" for x in u))'
```

---

## 2. The patch (4 hunks)

Adapt job/step names to the target repo; the **`with:` keys are what matter**.

### Hunk 1 — unique name on each wheel upload (matrix)

```diff
       - uses: actions/upload-artifact@v4
         with:
+          name: cibw-wheels-${{ matrix.os }}
           path: ./wheelhouse/*.whl
```

> If your matrix also splits by arch/python, include those too so the name is
> unique per leg, e.g. `name: cibw-wheels-${{ matrix.os }}-${{ matrix.arch }}`.

### Hunk 2 — unique name on the sdist upload

```diff
       - uses: actions/upload-artifact@v4
         with:
+          name: cibw-sdist
           path: dist/*.tar.gz
```

### Hunk 3 — download **all** artifacts and merge, then publish

```diff
       - uses: actions/download-artifact@v4
         with:
-          name: artifact
+          pattern: cibw-*
+          merge-multiple: true
           path: dist

-      - uses: pypa/gh-action-pypi-publish@v1.5.0
+      - uses: pypa/gh-action-pypi-publish@release/v1
         with:
           user: __token__
           password: ${{ secrets.PYPI_API_TOKEN }}
+          skip-existing: true
```

- `pattern: cibw-*` + `merge-multiple: true` collects every build artifact into
  one `dist/` directory (replaces the single `name: artifact`).
- Bump the publish action — `release/v1` tracks the latest `v1.x` (or pin a
  recent tag). **Required** for `skip-existing` to recognize PyPI's
  `400 "File already exists"` response instead of erroring on it.
- `skip-existing: true` makes re-runs idempotent (and enables backfills, §4).

### Hunk 4 (optional but recommended) — allow manual re-publish / backfill

```diff
 on:
   release:
     types: [created]
+  workflow_dispatch:        # manual re-publish / backfill
```

Then gate the build-upload + publish jobs on either event. Wherever a job/step
is currently gated like `if: github.event_name == 'release' ...`, widen it:

```yaml
if: (github.event_name == 'release' && github.event.action == 'created') || github.event_name == 'workflow_dispatch'
```

---

## 3. Reference: the corrected shape

```yaml
on:
  release:
    types: [created]
  workflow_dispatch:

jobs:
  build_wheels:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    steps:
      # ... build (e.g. pypa/cibuildwheel) ...
      - uses: actions/upload-artifact@v4
        with:
          name: cibw-wheels-${{ matrix.os }}
          path: ./wheelhouse/*.whl
          # if-no-files-found: error   # optional: fail loud on empty output

  build_sdist:
    steps:
      # ... build sdist ...
      - uses: actions/upload-artifact@v4
        with:
          name: cibw-sdist
          path: dist/*.tar.gz

  upload_pypi:
    needs: [build_wheels, build_sdist]
    steps:
      - uses: actions/download-artifact@v4
        with:
          pattern: cibw-*
          merge-multiple: true
          path: dist
      - uses: pypa/gh-action-pypi-publish@release/v1
        with:
          user: __token__
          password: ${{ secrets.PYPI_API_TOKEN }}
          skip-existing: true
```

---

## 4. Backfilling a version that already shipped incomplete

Once the patch is on the **default branch** (needed for `workflow_dispatch`):

1. Trigger the workflow manually:
   - GitHub UI: *Actions → the workflow → Run workflow*, or
   - CLI: `gh workflow run <workflow-file>.yml --ref <default-branch>`
2. It rebuilds every platform + sdist. `skip-existing: true` keeps the files
   already on PyPI and uploads only the missing ones (sdist, other-OS wheels).
3. Verify with the `curl … /json` snippet from §1.

Notes:
- A version's existing files can't be overwritten (PyPI filenames are
  immutable); you can only **add** the missing ones — which is exactly what
  this does.
- A partial upload from an earlier failed attempt is fine — a working
  `skip-existing` re-run is idempotent and finishes the rest.

---

## 5. Verify after applying

- [ ] `python -c "import yaml,sys; yaml.safe_load(open(sys.argv[1]))" <workflow>` parses.
- [ ] Push a branch / open a PR — the `pull_request` build path (if present)
      still builds wheels on every platform (it should not publish).
- [ ] On the next release (or a `workflow_dispatch` run), confirm the index has
      **both** an sdist and the expected wheels (the §1 snippet).
- [ ] Optional hardening: add `if-no-files-found: error` to each
      `upload-artifact`, and a post-publish step asserting the sdist is present.
