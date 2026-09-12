"""后台任务的小调度层。

为什么要它：向量化 800 个切片要调 80 多次接口，好几秒到几分钟，绝不能挂在 HTTP 请求里等。
三种执行方式按优先级：

1. 配了 Celery 且开关打开 → 进队列（生产路径，任务可重试、可观测）；
2. 没配 → 开一个守护线程就地跑（本机演示路径，请求立即返回）；
3. 线程也不行 → 同步跑（兜底，至少不会静默失败）。

前端统一靠轮询 `parse_status` 看进度，因此三种方式对前端完全透明 ——
这是刻意的：演示环境不该因为没起 Redis 就用不了。
"""
import threading
from typing import Any, Callable

from django.conf import settings
from django.db import close_old_connections


def _safe_run(func: Callable, args: tuple, kwargs: dict) -> None:
    """线程里跑任务。

    线程不共享请求的连接，所以要自己管连接的生命周期 —— 跑完必须关掉，
    否则连接池会一直涨到把 Postgres 的 max_connections 撑爆。
    """
    close_old_connections()
    try:
        func(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 —— 后台任务，异常只能记日志
        import logging

        logging.getLogger("rag").exception("后台任务执行失败: %s", exc)
    finally:
        close_old_connections()


def run_task(func: Callable, *args: Any, **kwargs: Any) -> str:
    """调度一个任务，返回实际采用的执行方式（celery / thread / sync）。"""
    if getattr(settings, "TASKS_USE_CELERY", False) and hasattr(func, "delay"):
        try:
            func.delay(*args, **kwargs)
            return "celery"
        except Exception:  # noqa: BLE001 —— broker 连不上就退到线程
            pass

    if getattr(settings, "TASKS_IN_THREAD", True):
        threading.Thread(
            target=_safe_run, args=(func, args, kwargs), daemon=True, name=f"task:{getattr(func, '__name__', 'job')}"
        ).start()
        return "thread"

    func(*args, **kwargs)
    return "sync"
