"""后台任务的小调度层。

为什么要它：向量化 800 个切片要调 80 多次接口，好几秒到几分钟，绝不能挂在 HTTP 请求里等。
三种执行方式按优先级：

1. 配了 Celery 且开关打开 → 进队列（生产路径，任务可重试、可观测）；
2. 没配 → 丢进**有上限的工作线程池**（本机演示路径，请求立即返回）；
3. 池不可用 → 同步跑（兜底，至少不会静默失败）。

线程池为什么要设上限：解析/向量化这类任务会同时占用一个数据库连接并持续调用模型接口，
早期实现是「一个任务一个新线程」，批量重新解析 50 条就是 50 个线程同时冲进去，
很容易把 Postgres 的 max_connections 和模型接口的速率限制一起撞爆。
现在固定 N 个常驻工作线程消费队列，超出部分排队等待，行为可预期。

前端统一靠轮询 `parse_status` 看进度，因此三种方式对前端完全透明 ——
这是刻意的：演示环境不该因为没起 Redis 就用不了。
"""
import atexit
import logging
import queue
import threading
from typing import Any, Callable

from django.conf import settings
from django.db import close_old_connections

logger = logging.getLogger("rag")

DEFAULT_MAX_WORKERS = 4

_queue: "queue.Queue[tuple[Callable, tuple, dict] | None]" = queue.Queue()
_workers: list[threading.Thread] = []
_workers_lock = threading.Lock()


def _max_workers() -> int:
    try:
        n = int(getattr(settings, "TASKS_MAX_WORKERS", DEFAULT_MAX_WORKERS))
    except (TypeError, ValueError):
        n = DEFAULT_MAX_WORKERS
    return max(1, min(n, 16))


def _safe_run(func: Callable, args: tuple, kwargs: dict) -> None:
    """工作线程里跑任务。

    线程不共享请求的连接，所以要自己管连接的生命周期 —— 跑完必须关掉，
    否则连接池会一直涨到把 Postgres 的 max_connections 撑爆。
    """
    close_old_connections()
    try:
        func(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 —— 后台任务，异常只能记日志
        logger.exception("后台任务执行失败: %s", exc)
    finally:
        close_old_connections()


def _worker_loop() -> None:
    while True:
        item = _queue.get()
        try:
            if item is None:  # 退出信号
                return
            func, args, kwargs = item
            _safe_run(func, args, kwargs)
        finally:
            _queue.task_done()


def _ensure_workers() -> None:
    """按需启动常驻工作线程。第一次调度任务时才起，不在 import 期起。"""
    if len(_workers) >= _max_workers():
        return
    with _workers_lock:
        while len(_workers) < _max_workers():
            t = threading.Thread(target=_worker_loop, daemon=True, name=f"task-worker-{len(_workers) + 1}")
            t.start()
            _workers.append(t)


@atexit.register
def _shutdown_workers() -> None:
    """进程退出时给工作线程发退出信号，别让解释器卡在 join 上。"""
    for _ in _workers:
        _queue.put(None)


def pending_count() -> int:
    """排队中的任务数，供健康检查/排查用。"""
    return _queue.qsize()


def run_task(func: Callable, *args: Any, **kwargs: Any) -> str:
    """调度一个任务，返回实际采用的执行方式（celery / thread / sync）。"""
    if getattr(settings, "TASKS_USE_CELERY", False) and hasattr(func, "delay"):
        try:
            func.delay(*args, **kwargs)
            return "celery"
        except Exception:  # noqa: BLE001 —— broker 连不上就退到线程池
            logger.warning("Celery 投递失败，回退到本地线程池")

    if getattr(settings, "TASKS_IN_THREAD", True):
        try:
            _ensure_workers()
            _queue.put_nowait((func, args, kwargs))
            return "pool"
        except Exception:  # noqa: BLE001 —— 池起不来的极端情况，退回同步
            logger.exception("线程池调度失败，改为同步执行")

    func(*args, **kwargs)
    return "sync"
