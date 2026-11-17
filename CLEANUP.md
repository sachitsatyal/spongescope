# Dev affordances removed

| Was there | Now |
|---|---|
| "Bundle location" text input in the sidebar | gone — the location is configuration, read from `SPONGESCOPE_BUNDLE` |
| "Per-site detail" expander whose button printed a note to myself | gone |
| "No local model: pasted-sequence scoring is disabled." caption | gone |
| nothing linking back to the model or the code | sidebar links to the model card and the repo |

The sidebar is now a scored-pair count, the lncRNA x miRNA dimensions, and two links.

The load error also changed. It used to print the raw `FileNotFoundError` next to an editable
path box, which invited a visitor to try fixing a configuration problem they cannot see the
cause of. Now it says the data could not be loaded and that the Space may still be starting,
with the technical detail below it — true, useful, and not an invitation.

Also deleted: the `load_model` helper and the `SpongeScope` type import, which only existed to
support the stub.

```powershell
cd $HOME\projects\spongescope
Expand-Archive -Path "$HOME\Downloads\spongescope-app-cleanup.zip" -DestinationPath . -Force
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

## One thing I did not remove

The **GitHub link points at a private repo**, so for anyone but you it is a 404. Either make the
repo public or tell me and I will drop that line. A dead link in the sidebar is worse than no
link, and this is the repo that contains the leakage-free evaluation and the two negative
results — the parts actually worth showing.
