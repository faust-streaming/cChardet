# Fixing a missing sdist / dropped wheels in `upload-artifact@v4` release workflows

A runbook for the failure mode where a PyPI release is **missing its source
distribution** (and often some wheels) even though **every CI job shows green**.

This is the bug that produced [faust-streaming/cChardet#41][issue] — the
`2.1.20` release shipped Linux wheels only, with no sdist and no macOS/Windows
wheels, from a workflow whose run reported `success`.

## Symptom

- A published release is missing files: no `*.tar.gz` sdist, and/or only one
  platform's wheels are present.
- The release workflow run is **green** — no job failed. The gap is silent.

## Root cause: the `upload-artifact` v3 → v4 behavior change

The classic "build fan-out → single publish job" layout looks like this:

```yaml
jobs:
  build_wheels:            # matrix over OSes
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    steps:
      - uses: actions/upload-artifact@v4     # no `name:`  -> defaults to "artifact"
        with:
          path: ./wheelhouse/*.whl

  build_sdist:
    steps:
      - uses: actions/upload-artifact@v4     # no `name:`  -> defaults to "artifact"
        with:
          path: dist/*.tar.gz

  upload_pypi:
    needs: [build_wheels, build_sdist]
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: artifact                     # <-- pulls ONE artifact only
          path: dist
      - uses: pypa/gh-action-pypi-publish@v1.x
```

- With **`upload-artifact@v3`**, several jobs uploading to the **same** artifact
  name were **merged** into one artifact. `download-artifact` by that name then
  got everything.
- With **`upload-artifact@v4`**, that implicit merge is **gone**. Each upload is
  its own artifact. When several jobs upload with the default name `artifact`,
  you end up with multiple separate artifacts that happen to share a name.
- `download-artifact@v4` with `name: artifact` resolves to **one** of them. The
  others — typically the sdist and the wheels from the slower-finishing OSes —
  are never handed to the publish step.

Because uploading and downloading both **succeed**, the run is green and the
missing files are only noticed later, on the index.

> In the cChardet case the release run produced **four** artifacts all named
> `artifact` (sdist, Windows wheels, macOS wheels, Linux wheels); the download
> grabbed only the Linux one, so PyPI got Linux wheels only.

## How to recognize it

Check the workflow for **all three** of these:

1. Two or more `upload-artifact@v4` steps with **no `name:`**, or the **same**
   `name:`.
2. A `download-artifact@v4` that selects by `name:` (a single artifact) rather
   than by `pattern:` with `merge-multiple: true`.
3. A publish/collect job that expects **all** build outputs in one directory.

Confirm the symptom from outside CI:

```bash
# Does the released version actually have an sdist?
curl -s https://pypi.org/pypi/<project>/<version>/json \
  | python3 -c 'import sys,json;u=json.load(sys.stdin)["urls"];
print("sdist:", any(x["packagetype"]=="sdist" for x in u));
print("wheels:", sum(x["packagetype"]=="bdist_wheel" for x in u))'
```

And inspect the release run's artifacts (GitHub UI → the run → *Artifacts*, or
the API `.../actions/runs/<run_id>/artifacts`). Multiple artifacts with the
**same name** is the smoking gun.

## The fix

Give every uploader a **unique** name, then download **all** of them and merge.

```yaml
jobs:
  build_wheels:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    steps:
      - uses: actions/upload-artifact@v4
        with:
          name: cibw-wheels-${{ matrix.os }}   # unique per matrix leg
          path: ./wheelhouse/*.whl
          # if-no-files-found: error            # optional: fail loud on empty output

  build_sdist:
    steps:
      - uses: actions/upload-artifact@v4
        with:
          name: cibw-sdist                      # unique
          path: dist/*.tar.gz

  upload_pypi:
    needs: [build_wheels, build_sdist]
    steps:
      - uses: actions/download-artifact@v4
        with:
          pattern: cibw-*                       # grab every build artifact
          merge-multiple: true                  # flatten them into one dir
          path: dist
      - uses: pypa/gh-action-pypi-publish@v1.x
        with:
          # skip-existing lets a re-run backfill missing files without failing
          # on files already on the index (see "Backfilling" below).
          skip-existing: true
```

Key points:

- **Unique names.** `${{ matrix.os }}` (and, if you split archs, the arch too)
  guarantees no collisions. `cibw-sdist` for the sdist.
- **`pattern:` + `merge-multiple: true`** replaces `name: artifact`. This is the
  canonical cibuildwheel-on-v4 pattern and collects every `cibw-*` artifact into
  `dist/`.
- **`skip-existing: true`** on the publish step makes re-runs idempotent.
- Optionally add **`if-no-files-found: error`** to `upload-artifact` so an empty
  wheelhouse fails the job instead of silently uploading nothing.

## Backfilling a version that already shipped incomplete

You cannot overwrite files already on PyPI (filenames are immutable, and a
deleted/yanked filename can't be reused). You *can* add the **missing** files to
an existing version. Two ways:

### A. Re-run the fixed workflow (recommended)

1. Land the fixed workflow on the default branch.
2. Add a `workflow_dispatch` trigger and let the build/publish jobs run for it,
   so you can re-publish on demand:

   ```yaml
   on:
     release:
       types: [created]
     workflow_dispatch:        # manual re-publish / backfill

   # gate the upload + publish jobs on either event:
   #   if: (github.event_name == 'release' && github.event.action == 'created')
   #       || github.event_name == 'workflow_dispatch'
   ```

3. Dispatch it. Every platform + the sdist rebuild; `skip-existing: true` means
   PyPI keeps the files already there and accepts only the missing ones.

> **`skip-existing` needs a recent publish action.** For a backfill, most files
> already exist, so `skip-existing` has to actually work. PyPI signals a
> duplicate with **`HTTP 400 Bad Request` "File already exists"** — and older
> `pypa/gh-action-pypi-publish` releases (e.g. `v1.5.0`) don't recognize that
> response, so they **error on the first pre-existing file instead of skipping
> it**. Use a current version (`pypa/gh-action-pypi-publish@release/v1`, or a
> recent pinned tag). A partially-completed publish is fine — a working
> `skip-existing` re-run is idempotent and finishes the rest.

### B. Re-use the artifacts already built

If the original run's artifacts are still retained, download the missing ones
(sdist, macOS/Windows wheels) and upload them directly:

```bash
twine upload --skip-existing dist/*
```

This avoids a rebuild but requires the artifacts still exist and a credential to
upload.

## Prevention

- Use the **unique-name + `pattern`/`merge-multiple`** pattern from the start on
  `upload-artifact@v4`. Treat any bare `name: artifact` download as a red flag.
- Add **`if-no-files-found: error`** so an empty artifact fails loudly.
- Add a **post-publish sanity check** — assert the index has both an sdist and
  the expected wheels for the new version (the `curl … /json` snippet above works
  well as a final workflow step or a release checklist item).
- Pin actions to a known-good version and read migration notes before bumping a
  major (this whole class of bug came from a v3 → v4 bump).

## References

- `actions/upload-artifact` — v4 migration notes (breaking change: no implicit
  same-name merge; `merge-multiple` on download).
- `pypa/cibuildwheel` — recommended GitHub Actions example (unique artifact
  names + `pattern`/`merge-multiple`).
- `pypa/gh-action-pypi-publish` — `skip-existing` option.

[issue]: https://github.com/faust-streaming/cChardet/issues/41
