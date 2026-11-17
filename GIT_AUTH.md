# "Password authentication in git is no longer supported"

Hugging Face disabled account passwords for git. A push needs an **access token** as the
password. On Windows there is a second trap: the credential manager caches the first answer and
replays it, so once a wrong credential is stored, every later attempt fails identically no
matter what you type.

Rather than fight that, push through the Hub API — you already have `HF_TOKEN` set and
`huggingface_hub` installed, and it is the same path the model and bundle uploads used.

```powershell
cd $HOME\projects\spongescope
Expand-Archive -Path "$HOME\Downloads\spongescope-push-space.zip" -DestinationPath . -Force

uv run python scripts\push_space.py --user sawcheet --dry-run
uv run python scripts\push_space.py --user sawcheet
```

It creates the Space (Docker SDK) if it does not exist and uploads the folder. No git, no
credential manager, no browser prompt. You do not need to create the Space in the web form
first — though if you already did, `exist_ok=True` means this just uploads into it.

Clean up the half-initialised git repo so it does not confuse things later:

```powershell
Remove-Item -Recurse -Force build\space\.git
```

## Then the variable

At <https://huggingface.co/spaces/sawcheet/spongescope/settings>, add a **variable** (not a
secret):

```
SPONGESCOPE_BUNDLE = hf://datasets/sawcheet/spongescope-demo
```

The app falls back to `data/demo` on local disk, which the Space does not have, so without this
every tab shows the missing-bundle error.

## If you would rather use git

It does work — the password is your token, not your account password:

```powershell
git remote set-url origin https://sawcheet:hf_yourtokenhere@huggingface.co/spaces/sawcheet/spongescope
git push -u origin main
```

That writes the token into `.git/config` in plaintext, so reset the URL afterwards:

```powershell
git remote set-url origin https://huggingface.co/spaces/sawcheet/spongescope
```

I would use the API script instead. Fewer places for a token to end up.

## The CRLF warnings

Harmless. Your `.gitattributes` normalises to LF on commit, which is what you want — the
Dockerfile and the app run on Linux.
