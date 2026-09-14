"""
Django 配置 —— 物联网学科大模型教学实验平台

配置项统一从环境变量读取，默认值适配本机开发环境（Homebrew PostgreSQL 16 + Redis）。
生产部署时复制 .env.example 为 .env 并覆盖。
"""
from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# 本地开发用 .env 覆盖默认值；不存在时静默跳过
load_dotenv(BASE_DIR / ".env")


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    return env(key, str(default)).lower() in ("1", "true", "yes", "on")


def env_int(key: str, default: int) -> int:
    try:
        return int(env(key, str(default)))
    except ValueError:
        return default


# --------------------------------------------------------------------------
# 基础
# --------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    # 无 models 的公共应用，放进来是为了让它的 management command（seed_demo）被自动发现
    "apps.common",
    "apps.accounts",
    "apps.configs",
    "apps.datasets",
    "apps.knowledge",
    "apps.agents",
    "apps.audit",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --------------------------------------------------------------------------
# 数据库
# --------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "iot_edu_platform"),
        "USER": env("DB_USER", os.environ.get("USER", "postgres")),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", "127.0.0.1"),
        "PORT": env("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

# --------------------------------------------------------------------------
# 国际化
# --------------------------------------------------------------------------
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------
# 静态与媒体
# --------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))

# --------------------------------------------------------------------------
# CORS（前端 Vite 开发服务器）
# --------------------------------------------------------------------------
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    o.strip() for o in env(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",") if o.strip()
]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# --------------------------------------------------------------------------
# Redis / Celery
# --------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", "redis://127.0.0.1:6379/0")
CELERY_BROKER_URL = env("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
# broker 连不上时快速失败，好让调度层及时退回到线程模式
CELERY_BROKER_CONNECTION_TIMEOUT = 2.0

# 后台任务的执行方式（见 apps/common/tasks.py）
# TASKS_USE_CELERY=False 时，长任务进本地工作线程池，请求立即返回、前端轮询状态。
# 生产环境起了 worker 之后把 USE_CELERY 打开即可，前端无需改动。
TASKS_USE_CELERY = env_bool("TASKS_USE_CELERY", False)
TASKS_IN_THREAD = env_bool("TASKS_IN_THREAD", True)
# 本地工作线程池的并发上限：任务会各占一个数据库连接并调用模型接口，
# 不设上限时批量操作（如批量重新解析）会把连接数和接口限流一起撞爆。
TASKS_MAX_WORKERS = env_int("TASKS_MAX_WORKERS", 4)

# 聊天接口的每用户限流（次/分钟）：流式问答消耗 token，
# 不设闸门时单个账号可以无限发起。0 表示不限制。
CHAT_RATE_LIMIT_PER_MINUTE = env_int("CHAT_RATE_LIMIT_PER_MINUTE", 20)

# --------------------------------------------------------------------------
# 平台业务配置
# --------------------------------------------------------------------------
# 向量维度：换 embedding 模型时需要同步调整并重新生成迁移
EMBEDDING_DIM = env_int("EMBEDDING_DIM", 1024)

# 大模型 / Embedding 服务（云端 API，OpenAI 兼容协议）
LLM_BASE_URL = env("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_API_KEY = env("LLM_API_KEY", "")
LLM_MODEL = env("LLM_MODEL", "deepseek-chat")

EMBEDDING_BASE_URL = env("EMBEDDING_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
EMBEDDING_API_KEY = env("EMBEDDING_API_KEY", "")
EMBEDDING_MODEL = env("EMBEDDING_MODEL", "text-embedding-v3")

# 检索默认参数
RETRIEVAL_TOP_K = env_int("RETRIEVAL_TOP_K", 5)
RETRIEVAL_SCORE_THRESHOLD = float(env("RETRIEVAL_SCORE_THRESHOLD", "0.0"))

# 切片默认参数
CHUNK_SIZE = env_int("CHUNK_SIZE", 500)
CHUNK_OVERLAP = env_int("CHUNK_OVERLAP", 80)

# 允许上传的数据格式
ALLOWED_UPLOAD_FORMATS = [
    "docx", "doc", "pdf", "txt", "md", "epub", "xlsx", "xls", "csv", "html",
]
MAX_UPLOAD_SIZE_MB = env_int("MAX_UPLOAD_SIZE_MB", 200)

# --------------------------------------------------------------------------
# 日志
# --------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "[{levelname}] {asctime} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        "rag": {"level": "DEBUG" if DEBUG else "INFO", "handlers": ["console"], "propagate": False},
    },
}
