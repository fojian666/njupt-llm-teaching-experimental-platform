# 物联网学科大模型教学实验平台

面向高校物联网专业的 **RAG 学科知识库问答平台**：把教材、培养方案、学院规章等散落的学科资料，
变成**能溯源到章节的问答系统**。全部 RAG 逻辑（解析 / 切片 / 向量化 / 混合检索 / 流式生成 / 引用抽取）
为自研实现，不依赖 LangChain、Dify 等框架。

核心链路：

```
上传 → 解析（含 OCR）→ 按章节结构切片 → 向量化（pgvector / HNSW）
     → 混合检索（向量 + BM25 关键词，α 加权融合）→ 编号提示词 → 流式回答 → 引用溯源
```

四大模块：**数据管理**（数据分类管理 / 数据资源）、**智能体中心**（智能体广场 / 对话）、
**知识管理**（知识库 / 切片 / 检索调试）、**配置与治理**（模型配置 / 问答记录 / 使用统计）。

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Django 5.2 LTS + Django Ninja（RAG 逻辑独立在 `backend/rag/` service 层） |
| 存储 | PostgreSQL 16 + pgvector（向量与业务数据同库，HNSW 索引） |
| 异步 | 线程池（`apps/common/tasks.py`）。requirements 里的 Redis/Celery 为预留，当前未启用，可不装 |
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + Pinia |
| 模型 | 一切走 OpenAI 兼容协议：DeepSeek / 通义千问 / 本地 BGE 均可，页面上可切换 |

## 快速开始

前置：Python 3.11+（开发环境 3.13）、Node 18+、PostgreSQL 16 且已安装 pgvector 扩展。

```bash
# 1) 数据库：建库并启用向量扩展
createdb iot_edu_platform
psql -d iot_edu_platform -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 2) 后端
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env        # ← 必改：DB_USER/DB_PASSWORD 改成你自己的数据库账号
.venv/bin/python manage.py migrate

# 3) 灌入演示数据（账号 / 分类树 / 知识库 / 仓库内语料 / 切片向量化 / 示例智能体）
.venv/bin/python manage.py seed_demo

# 4) 前端
cd ../frontend
npm install

# 5) 一键启动（前后端一起）
cd .. && ./start.sh
```

打开 http://127.0.0.1:5173 ，登录 `admin / admin123`（教师 `teacher/teacher123`、学生 `student/student123`）。

> **`.env` 必改项**：`DB_USER` / `DB_PASSWORD`（示例里默认是作者本机的用户名）。
> 大模型 Key：`LLM_API_KEY`（问答用，DeepSeek）与 `EMBEDDING_API_KEY`（向量化用，通义）
> 至少配一个向量方案的 Key，否则切片无法向量化（见下一节的零成本替代）。
> `EMBEDDING_DIM=1024` 必须与向量模型输出维度一致，换模型要重建向量。

## 没有模型 Key？跑一个零成本的本地向量服务

`backend/embedding_server.py` 是一个 OpenAI 兼容的本地 embedding 服务（BGE，1024 维，CPU 可跑），
向量化**零 token 消耗**：

```bash
.venv/bin/pip install sentence-transformers   # 会拉 torch，体积较大
.venv/bin/python embedding_server.py          # 首次自动从 hf-mirror 下载约 1.3GB 模型
```

然后把 `.env` 里向量三件套指向它：

```
EMBEDDING_BASE_URL=http://127.0.0.1:18090/v1
EMBEDDING_API_KEY=local
EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5
```

注意：问答的 LLM（`LLM_API_KEY`）目前没有本地替代，仍需一个 OpenAI 兼容的对话模型 Key。

## 一键脚本

```bash
./start.sh            # 前后端一起启动（Ctrl+C 一起停）
./start.sh back       # 只起后端    ./start.sh front   # 只起前端
./start.sh status     # 查看两端运行状态
./start.sh stop       # 停掉本项目的前后端进程
RELOAD=1 ./start.sh   # 后端代码热重载（默认关闭）
```

端口：后端 `127.0.0.1:8000`（API 文档 `/api/docs`），前端 `127.0.0.1:5173`（`/api` 已代理到后端）。
日志在 `.logs/`。脚本对"端口已被本项目进程占用"的情况会自动复用而不是报错退出。

## 演示数据说明

`seed_demo` 只灌**仓库里真实存在的文件**，不造假数据。clone 后你会拿到：

- ✅ 4 份学院文件（学院简介 + 3 份专业培养方案，docx/doc）
- ✅ `示例语料/` 4 篇原创物联网短文（保证没有教材也能把全链路跑通）
- ❌ 两本教材（扫描版 PDF / epub）与 OCR 产物——**因版权与体积被 `.gitignore` 排除**
  ，seed 时会自动跳过并提示。想复现教材问答，把文件放到仓库根目录对应文件名后再跑 seed。

常用变体：

```bash
.venv/bin/python manage.py seed_demo --reset             # 清空业务数据重来
.venv/bin/python manage.py seed_demo --skip-index        # 只建元数据，不切片向量化（没配 Key 时用）
.venv/bin/python manage.py seed_demo --reset-passwords   # 演示账号密码重置为 admin123 等
```

## 目录结构

```
├── start.sh                # 一键启动/停止/状态
├── backend/
│   ├── config/             # Django 配置（读 .env）
│   ├── apps/
│   │   ├── agents/         # 智能体 / 会话 / SSE 流式问答
│   │   ├── datasets/       # 分类树 / 数据资源 / 标签 / 解析
│   │   ├── knowledge/      # 知识库 / 切片 / 检索调试
│   │   ├── configs/        # 模型供应商 / 模型 / 系统参数
│   │   ├── audit/          # 问答记录 / 操作日志 / 统计
│   │   ├── accounts/       # 账号与角色（admin/teacher/student）
│   │   └── common/         # 通用：分页、操作日志、线程任务
│   ├── rag/                # 自研 RAG 核心：parsers(解析) splitter(切片)
│   │                       #   store(向量检索) retriever(混合检索) generator(生成) providers(模型接入)
│   ├── eval_retrieval.py   # 检索质量评测（15 题 × 4 配置，不调 LLM 零 token）
│   └── embedding_server.py # 零成本本地向量服务
├── frontend/               # Vue3 前端（views/ 与后端四大模块一一对应）
└── 示例语料/                # 随仓库分发的原创语料（seed_demo 会自动灌入）
```

## 常用工具与文档

| 文件 | 用途 |
|---|---|
| `backend/eval_retrieval.py` | 检索质量评测：术语型/口语化两组题，对比混合 / 纯向量 / 纯关键词 / 降级四种配置的 Hit@1/3/5 |
| `检索评测报告.md` | 上面脚本的产物（可复现），含"混合检索 Hit@1 反而低于纯向量"的根因分析 |
| `演示脚本.md` | 7 分钟视频演示的分镜、话术、预置问题与兜底方案 |
| `backend/reembed_all.py` | 全量重建切片向量（换向量模型后用） |

## 关于 Redis / Celery（高并发预留）

当前**不依赖 Redis 也能完整运行**：文档解析、切片、向量化这类长任务由
`apps/common/tasks.py#run_task` 调度，默认用守护线程就地执行、请求立即返回，
前端靠轮询 `parse_status` 看进度——因此执行方式对前端完全透明。

任务队列的开关已预留（`apps/common/tasks.py` 的 Celery 分支含 broker 失联自动降级）：

```
TASKS_USE_CELERY=true    # .env 里打开即走 Celery（还需补 celery app 与 @shared_task 注册）
TASKS_IN_THREAD=false    # 关掉线程兜底，强制走队列/同步
```

**什么时候值得上**：多人同时上传大文件解析、需要任务重试/优先级/可观测时。
单机演示与小班教学场景下，线程方案足够，少两个常驻组件（broker + worker）。
另外，真正的生产并发瓶颈顺序是：① `runserver` 换 gunicorn/uvicorn 多 worker；
② LLM/嵌入上游的吞吐与限流；③ Postgres 连接数（考虑 pgbouncer）；
④ 才是任务队列与缓存——先看 ①②③，不要从 Redis 开始优化。

## 已知边界

- **pgvector 安装**：Homebrew 的 pgvector bottle 可能对应与其捆绑的 PG 版本；若你的 PG16 是 brew 装的而
  `CREATE EXTENSION vector` 报错，需要针对 PG16 源码编译安装 pgvector（本仓库作者环境即如此）。
- **中文分词**：未引入 jieba（sdist 在部分机器 pip 解包失败），检索的关键词通道用的是自研字符
  bigram 分词器（`rag/tokenizer.py`），零依赖。
- **OCR**：扫描版 PDF 没有文字层，需要先 OCR（作者用 macOS Vision 框架完成，产物未入库）。
- 前端主包约 1.1MB，大头是 Element Plus 全量引入；问答页已按需加载（201 kB）。
  进一步优化需引入 `unplugin-vue-components` 按需加载（未做）。
