# 阶段一：运行时镜像（默认，MOCK 可离线全链路）
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖以利用镜像层缓存（requirements.txt 仅含运行时依赖）
COPY requirements.txt requirements-eval.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-eval.txt

COPY app ./app

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000"]

# 阶段二：acceptance 档（真实 Docling 解析验收用；镜像约 +1GB，不进入默认栈）
# 构建：docker build --target acceptance -t docrag-acceptance-backend:acceptance ./backend
FROM runtime AS acceptance

# Docling 的 PDF/OCR 依赖链需要 X11/GL 客户端库（libxcb/libGL 等）与 glib
RUN apt-get update && apt-get install -y --no-install-recommends \
      libxcb1 libxcb-render0 libxcb-shm0 libxcb-xfixes0 libxcb-shape0 \
      libxcb-randr0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
      libxcb-xinerama0 libxcb-xkb1 libx11-6 libglib2.0-0 \
      libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# 允许 pip 缓存加速 acceptance 重建（runtime 的 PIP_NO_CACHE_DIR=1 在此覆盖）
RUN PIP_NO_CACHE_DIR=0 pip install docling==2.117.0

# 首次真实解析时 Docling 自动下载模型（layout ~172MB + TableFormer ~358MB）
# 建议挂载模型缓存目录（~/.cache/docling，见 docs/DEPLOYMENT.md）
ENV RAG_PARSE_MOCK=false
