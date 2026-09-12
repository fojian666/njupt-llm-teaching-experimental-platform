"""本地 embedding 服务 —— OpenAI 兼容协议，零 token 消耗。

用法：
    backend/.venv/bin/python backend/embedding_server.py [端口，默认 18090]

接口：POST /v1/embeddings
    body: {"input": ["文本1", "文本2", ...], "model": "bge-large-zh-v1.5"}
    resp: {"data": [{"index": 0, "embedding": [...]}, ...], "model": ..., "usage": {"total_tokens": n}}

模型：BAAI/bge-large-zh-v1.5（1024 维，与数据库 EMBEDDING_DIM 一致）。
首次运行会自动从 hf-mirror.com 下载模型（约 1.3GB）到 ~/.cache/huggingface。
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18090
MODEL_NAME = "BAAI/bge-large-zh-v1.5"

print(f"[embedding-server] 加载模型 {MODEL_NAME}（首次会从 hf-mirror 下载约 1.3GB）...", flush=True)
_t0 = time.time()

# 必须在 import sentence_transformers 之前设置镜像
import os
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from sentence_transformers import SentenceTransformer  # noqa: E402

model = SentenceTransformer(MODEL_NAME, device="cpu")
print(f"[embedding-server] 模型加载完成，耗时 {time.time() - _t0:.1f}s，维度 {model.get_sentence_embedding_dimension()}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 安静一点
        pass

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"ok": True, "model": MODEL_NAME})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/embeddings":
            self._json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            inputs = body.get("input")
            if isinstance(inputs, str):
                inputs = [inputs]
            if not inputs:
                self._json(400, {"error": {"message": "input 不能为空"}})
                return
            vectors = model.encode(inputs, batch_size=32, normalize_embeddings=True,
                                   show_progress_bar=False).tolist()
            self._json(200, {
                "object": "list",
                "data": [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vectors)],
                "model": body.get("model") or MODEL_NAME,
                "usage": {"prompt_tokens": sum(len(t) for t in inputs), "total_tokens": sum(len(t) for t in inputs)},
            })
        except Exception as e:  # noqa: BLE001
            self._json(500, {"error": {"message": str(e)}})

    def _json(self, code: int, obj: dict):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    print(f"[embedding-server] 监听 http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
