# 物联网学科大模型教学实验平台

面向物联网专业的学科知识库问答平台。把教材、培养方案、学院文件等资料导入知识库，
学生提问时先检索相关片段，再由大模型生成带引用来源的回答。

RAG 部分是自研实现（解析、切片、向量化、混合检索、生成、引用抽取），没有用 LangChain 或 Dify，
代码集中在 `backend/rag/`，想改检索策略或换模型看这个目录。

功能分四块：数据管理（分类、数据资源）、智能体中心（广场、对话）、
知识管理（知识库、切片、检索调试）、配置与治理（模型配置、问答记录、统计）。

## 环境

- Python 3.11+（开发用的 3.13）
- Node 18+
- PostgreSQL 16，装好 pgvector 扩展
- Redis 暂时不需要，见文末说明

## 快速开始

1. 建库，启用 vector 扩展：

```bash
createdb iot_edu_platform
psql -d iot_edu_platform -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

2. 配置后端。把 `.env.example` 复制成 `backend/.env`，改这几处：
   - `DB_USER` / `DB_PASSWORD`：改成你自己的数据库账号（示例里是我本机的）
   - `LLM_API_KEY`：对话模型 Key，DeepSeek / 通义等 OpenAI 兼容服务都行
   - `EMBEDDING_API_KEY`：向量化模型 Key。没有的话见下文"本地向量服务"

3. 装依赖、建表、灌演示数据：

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo
```

4. 前端：

```bash
cd frontend
npm install
```

5. 启动：

```bash
./start.sh
```

打开 http://127.0.0.1:5173 ，登录 `admin / admin123`（教师 teacher/teacher123，学生 student/student123）。

后端 API 文档在 http://127.0.0.1:8000/api/docs 。

## 本地向量服务（不配 Key 的办法）

向量化可以走本地服务，不调外部接口。`backend/embedding_server.py` 是一个 OpenAI 兼容的
embedding 服务，用 BGE 模型（1024 维，CPU 能跑）：

```bash
cd backend
.venv/bin/pip install sentence-transformers   # 会带上 torch，比较大
.venv/bin/python embedding_server.py          # 首次启动从 hf-mirror 下载约 1.3GB 模型
```

然后 `.env` 里向量三件套改成：

```
EMBEDDING_BASE_URL=http://127.0.0.1:18090/v1
EMBEDDING_API_KEY=local
EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5
```

对话模型没有本地替代，`LLM_API_KEY` 还是要配一个。

## start.sh

```bash
./start.sh            # 前后端一起启动，Ctrl+C 一起停
./start.sh back       # 只起后端
./start.sh front      # 只起前端
./start.sh status     # 看两端运行状态
./start.sh stop       # 停掉本项目的前后端
RELOAD=1 ./start.sh   # 后端代码热重载（默认关）
```

端口：后端 127.0.0.1:8000，前端 127.0.0.1:5173（/api 代理到后端）。日志在 `.logs/`。

## 演示数据

`seed_demo` 只导入仓库里实际存在的文件，不造假数据。仓库里有 4 份学院文件
（学院简介和 3 份培养方案）加 `示例语料/` 下 4 篇短文，够把全链路跑通。
两本教材（扫描版 PDF 和 epub）因为版权没放进仓库，seed 时会自动跳过并提示。

```bash
.venv/bin/python manage.py seed_demo --reset             # 清空业务数据重来
.venv/bin/python manage.py seed_demo --skip-index        # 跳过向量化，没配 Key 时用
.venv/bin/python manage.py seed_demo --reset-passwords   # 演示账号密码重置
```

## 其他脚本和文档

- `backend/eval_retrieval.py`：检索质量评测，15 道题对比混合 / 纯向量 / 纯关键词 / 降级四种配置的命中率，不调大模型。结果写在 `检索评测报告.md`
- `backend/reembed_all.py`：换向量模型后全量重建切片向量
- `演示脚本.md`：7 分钟演示视频的分镜和话术

## 几个已知问题

- Homebrew 装的 pgvector 不一定对应你的 PG 版本，`CREATE EXTENSION vector` 报错的话，需要针对 PG16 源码编译安装
- 中文分词没用 jieba（部分机器 pip 装不上），检索的关键词通道用的是自研的字符 bigram 分词，见 `rag/tokenizer.py`
- 扫描版 PDF 没有文字层，要先 OCR 才能入库。我们用 macOS Vision 做的，OCR 产物没进仓库
- 前端主包约 1.1MB，主要是 Element Plus 全量引入。要优化得引入 unplugin-vue-components，暂时没做

## Redis / Celery

现在不需要 Redis。解析、向量化这类耗时任务由 `apps/common/tasks.py` 的 `run_task`
调度，默认开守护线程执行，请求立即返回，前端轮询 parse_status 看进度。

以后并发上来了想换 Celery，开关已经留好：settings 里有 `TASKS_USE_CELERY`，
run_task 的 Celery 分支也写好了，broker 连不上会自动退回线程。到时候要补的是
celery app 实例、任务函数加 @shared_task、`.env` 里 `TASKS_USE_CELERY=true`，再起 worker。

并发真上来的时候，先看三件事：runserver 换 gunicorn 多 worker、模型上游的吞吐和限流、
Postgres 连接数。这些都在任务队列前面。
