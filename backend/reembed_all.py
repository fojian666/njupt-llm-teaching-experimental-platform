"""把全部切片用本地 embedding 服务重新向量化（覆盖旧的 mock 向量）。

用法：backend/.venv/bin/python backend/reembed_all.py
依赖：backend/embedding_server.py 已在 18090 端口运行。
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import django  # noqa: E402

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from rag.providers import embedding_from_settings  # noqa: E402
from rag.store import save_embeddings  # noqa: E402
from apps.knowledge.models import Chunk  # noqa: E402

BATCH = 32

def main() -> None:
    provider = embedding_from_settings()
    print(f"embedding 服务: {provider.base_url} / {provider.model}", flush=True)
    # 连通性测试
    dim = len(provider.embed(["ping"])[0])
    print(f"连通正常，向量维度 {dim}", flush=True)

    total = Chunk.objects.count()
    done = 0
    t0 = time.time()
    ids = list(Chunk.objects.order_by("id").values_list("id", flat=True))
    for i in range(0, len(ids), BATCH):
        batch_ids = ids[i : i + BATCH]
        rows = list(Chunk.objects.filter(id__in=batch_ids).values("id", "content"))
        vectors = provider.embed([r["content"] for r in rows])
        save_embeddings(list(zip([r["id"] for r in rows], vectors)))
        done += len(rows)
        if (i // BATCH) % 10 == 0 or done == total:
            speed = done / max(time.time() - t0, 0.1)
            print(f"进度 {done}/{total}（{speed:.0f} 条/秒）", flush=True)
    print(f"完成：{done} 条切片已重新向量化，耗时 {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
