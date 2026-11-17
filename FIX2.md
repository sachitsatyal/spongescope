# Why the same error came back

`build_space.py` never rebuilt. Its first step is to delete the previous `build/space`, and that
hit the `.git` directory left by the earlier `git init`. Git marks objects under `.git`
**read-only**, and on Windows `os.unlink` then fails with `Access is denied`.

So the build died, `build/space` kept the **old** README, and `push_space.py` uploaded exactly
what it found — the 64-character description again. The fix had been applied to `spaces/README.md`
and never reached the folder being pushed.

Now `rmtree` clears the read-only bit and retries, so a stale `.git` cannot silently preserve a
previous build. Verified by creating a `.git` with read-only objects and confirming the rebuild
goes through and the new description lands.

The deeper problem was that a failed build left usable-looking output. Two commands in one block
meant the push did not know the build had failed. Worth running them separately when the first
one has any chance of failing.

```powershell
cd $HOME\projects\spongescope
Expand-Archive -Path "$HOME\Downloads\spongescope-space-fix2.zip" -DestinationPath . -Force

uv run python scripts\build_space.py --user sawcheet
```

Check that it printed the five files, then:

```powershell
uv run python scripts\push_space.py --user sawcheet
```

Then the variable at <https://huggingface.co/spaces/sawcheet/spongescope/settings>:

```
SPONGESCOPE_BUNDLE = hf://datasets/sawcheet/spongescope-demo
```
