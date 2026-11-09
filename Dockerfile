FROM ghcr.io/astral-sh/uv:0.8.22 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY app.py research.py store.py acb.py context_panel.py context-panel.js index.html style.css app.js ./
COPY data ./data
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8080
CMD ["python", "app.py"]
