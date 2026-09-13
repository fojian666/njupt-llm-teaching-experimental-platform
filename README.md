# 物联网学科大模型教学实验平台

面向物联网专业的学科知识库问答平台。教材、培养方案、学院文件等资料导入知识库后，
学生提问先检索相关片段，再由大模型生成带引用来源的回答。

解析、切片、向量化、混合检索、生成、引用抽取均为自研实现，代码集中在 `backend/rag/`，
没有依赖 LangChain 或 Dify。修改检索策略或更换模型从这一层入手。

功能分为四个模块：

- 数据管理：数据分类、数据资源
- 智能体中心：智能体广场、对话
- 知识管理：知识库、切片、检索调试
- 配置与治理：模型配置、问答记录、统计

## 环境

- Python 3.11 及以上，开发环境为 3.13
- Node 18 及以上
- PostgreSQL 16，安装 pgvector 扩展
- Redis 暂时不需要，见文末说明

## 快速开始

1. 建库并启用 vector 扩展：

```bash
createdb iot_edu_platform
psql -d iot_edu_platform -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

2. 配置后端。把 `.env.example` 复制为 `backend/.env`，修改以下项：
   - `DB_USER` / `DB_PASSWORD`：数据库账号密码，按本机实际情况填写
   - `LLM_API_KEY`：对话模型 Key，DeepSeek、通义等 OpenAI 兼容服务均可
   - `EMBEDDING_API_KEY`：向量化模型 Key，暂无时可使用下文的本地向量服务

3. 安装依赖、建表、灌入演示数据：

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

打开 http://127.0.0.1:5173 ，账号 `admin / admin123`。教师账号 `teacher / teacher123`，
学生账号 `student / student123`。后端 API 文档在 http://127.0.0.1:8000/api/docs 。

## 本地向量服务

向量化可以走本地服务，不调用外部接口。`backend/embedding_server.py` 提供 OpenAI 兼容的
embedding 接口，使用 BGE 模型，1024 维，CPU 即可运行：

```bash
cd backend
.venv/bin/pip install sentence-transformers   # 依赖 torch，体积较大
.venv/bin/python embedding_server.py          # 首次启动从 hf-mirror 下载约 1.3GB 模型
```

`.env` 中向量相关配置改为：

```
EMBEDDING_BASE_URL=http://127.0.0.1:18090/v1
EMBEDDING_API_KEY=local
EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5
```

对话模型没有本地替代方案，`LLM_API_KEY` 仍需配置。

## start.sh

```bash
./start.sh            # 前后端一起启动，Ctrl+C 一起停止
./start.sh back       # 只启动后端
./start.sh front      # 只启动前端
./start.sh status     # 查看运行状态
./start.sh stop       # 停止本项目的前后端
RELOAD=1 ./start.sh   # 后端代码热重载，默认关闭
```

端口：后端 127.0.0.1:8000，前端 127.0.0.1:5173，/api 由代理转发到后端。日志在 `.logs/`。

## 演示数据

`seed_demo` 只导入仓库中实际存在的文件，不使用虚构数据。仓库内包含 4 份学院文件，
即学院简介与 3 份专业培养方案，另有 `示例语料/` 目录下 4 篇短文，足够跑通全部链路。
两本教材为扫描版 PDF 与 epub，因版权原因未放入仓库，seed 时会自动跳过并给出提示。

```bash
.venv/bin/python manage.py seed_demo --reset             # 清空业务数据重来
.venv/bin/python manage.py seed_demo --skip-index        # 跳过向量化，没配 Key 时用
.venv/bin/python manage.py seed_demo --reset-passwords   # 演示账号密码重置
```

## 其他脚本与文档

- `backend/eval_retrieval.py`：检索质量评测，15 道题对比混合、纯向量、纯关键词、降级四种配置的命中率，不调用大模型。结果写入 `检索评测报告.md`
- `backend/reembed_all.py`：更换向量模型后全量重建切片向量
- `演示脚本.md`：7 分钟演示视频的分镜与话术

## 已知问题

- Homebrew 安装的 pgvector 未必与所装 PG 版本匹配，`CREATE EXTENSION vector` 报错时，需要针对 PG16 源码编译安装
- 中文分词未使用 jieba，部分环境下 pip 安装会失败。检索的关键词通道采用自研的字符 bigram 分词，见 `rag/tokenizer.py`
- 扫描版 PDF 没有文字层，入库前需要 OCR。OCR 使用 macOS Vision 完成，产物未纳入仓库
- 前端主包约 1.1MB，主要来自 Element Plus 全量引入。优化需要引入 unplugin-vue-components，尚未处理

## Redis 与 Celery

当前不需要 Redis。解析、向量化等耗时任务由 `apps/common/tasks.py` 的 `run_task`
调度，默认以守护线程执行，请求立即返回，前端轮询 parse_status 查看进度。

并发规模扩大后切换 Celery 的开关已预留：settings 中有 `TASKS_USE_CELERY`，
run_task 的 Celery 分支已实现，broker 连接失败会自动退回线程。届时需要补齐
celery app 实例、任务函数加 @shared_task、`.env` 中 `TASKS_USE_CELERY=true`，并启动 worker。

并发上来之后优先排查的是：runserver 换 gunicorn 多 worker、模型上游的吞吐与限流、
Postgres 连接数。这三项都在任务队列之前。
