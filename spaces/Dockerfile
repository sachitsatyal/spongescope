# Streamlit on Hugging Face Spaces.
#
# The Streamlit SDK was deprecated in April 2025, so a Streamlit app ships as a Docker Space.
# Two things Spaces requires that a normal Dockerfile would not bother with:
#   * the container runs as uid 1000, not root, so anything written at runtime must live
#     somewhere that user owns -- hence HOME and the explicit cache paths;
#   * the app must listen on the port declared as app_port in README.md (8501 here) and bind
#     0.0.0.0, or the Space builds fine and then times out as "not responding".
FROM python:3.11-slim

# curl is for the healthcheck below; python:3.11-slim does not ship it, and a HEALTHCHECK that
# cannot run marks the container unhealthy rather than failing loudly.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    # huggingface_hub caches the demo bundle here; without a writable HF_HOME the first
    # hf_hub_download fails with a permission error rather than anything self-explanatory.
    HF_HOME=/home/user/.cache/huggingface \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR $HOME/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY --chown=user app ./app

EXPOSE 8501

# A healthcheck Spaces can use, and a quick way to tell "still installing" from "crashed".
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app/streamlit_app.py"]
