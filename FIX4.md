# The test was right and my fix was half a fix

`str(Path("hf://datasets/u/r"))` is **platform-dependent**:

| platform | result |
|---|---|
| POSIX | `hf:/datasets/u/r` |
| Windows | `hf:\datasets\u\r` |

I only accepted the POSIX form, so the guard passed in my Linux sandbox and failed on yours.
`resolve_bundle` now normalises separators before the prefix check, and the test asserts three
spellings — doubled slash, single slash, and whatever this platform's `Path` produces — so it
fails on the OS where the guard is actually broken rather than silently passing on the other one.

This could not have broken the Space: that runs Linux, and the app no longer puts the location
through `Path` at all. It is the belt-and-braces check that was broken, which is worth fixing
precisely because its whole job is to catch the case nobody is thinking about.

```powershell
cd $HOME\projects\spongescope
Expand-Archive -Path "$HOME\Downloads\spongescope-space-fix4.zip" -DestinationPath . -Force
uv run pytest tests\test_demo_data.py -q
```

8 passed, then:

```powershell
uv run python scripts\build_space.py --user sawcheet
```

Five files, then:

```powershell
uv run python scripts\push_space.py --user sawcheet
```

That should be the last one. The Space rebuilds, the variable is already set, and the first load
pulls 12 MB before caching it.
