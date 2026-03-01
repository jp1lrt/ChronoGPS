# shutdown_manager.py
# =============================================================================
# ChronoGPS v2.5 (Phase 1) - Shutdown Manager
#
# 【目的 / Why】
# - v2.5「案2：監視起動 + 昇格再起動」において、旧プロセスが確実に終了することは必須。
# - ChronoGPSは after() タイマー、シリアルポート、ワーカースレッド等を使っているため、
#   単純な root.destroy() だけでは “ゾンビ化（プロセスが残る）” しやすい。
#
# 【設計方針（最小侵襲 / non-invasive）】
# - 既存コードの停止ロジックを全面改修しない。
# - shutdown_manager.py では「停止に必要なものを登録しておき、最後に一括で止める」だけを提供する。
# - 登録は GUI / time_sync / tray 等の既存コード側で “最小差分” で行う。
#
# 【使い方（予定）】
# - アプリ起動時に ShutdownManager を1つ生成し、各所で以下を登録:
#   - after() の戻りID      → register_after(root, after_id)
#   - 停止イベント(Event)   → register_stop_event(event)
#   - thread               → register_thread(thread)
#   - serial等 closeable   → register_closeable(obj)  (close()/stop()/shutdown() を呼ぶ)
#   - tray icon等          → register_callback(func)  (明示停止が必要なもの)
# - 昇格成功時など、終了したいとき:
#   - shutdown_manager.shutdown(root, reason="handoff_to_elevated")
#
# 【重要】
# - “確実な終了” のため、最後の手段として os._exit(0) を用意している。
#   ただし乱暴なので、通常は force=False のまま使用し、
#   どうしても残る環境があった場合のみ force=True を検討する。
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Any, List
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)


@dataclass
class ShutdownManager:
    """
    既存コードへの侵襲を最小にするための「停止の集約点」。

    このクラスは “何を止めるか” を登録するだけで、
    実際の停止処理は shutdown() にまとめて実行する。
    """

    # Tk after() id を cancel するために (root, after_id) のペアで持つ
    _after_tasks: List[tuple[Any, str]] = field(default_factory=list)

    # threading.Event などの stop signal
    _stop_events: List[Any] = field(default_factory=list)

    # join 対象の thread
    _threads: List[threading.Thread] = field(default_factory=list)

    # close()/stop()/shutdown() を持つ “closeable” を登録（serial等）
    _closeables: List[Any] = field(default_factory=list)

    # 明示停止用コールバック（tray.stop など）
    _callbacks: List[Callable[[], None]] = field(default_factory=list)

    # shutdown が二重に走らないためのガード
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _started: bool = False

    def register_after(self, root: Any, after_id: Optional[str]) -> None:
        """
        Tkinter root.after() の戻り値 ID を登録する。
        """
        if root is None or not after_id:
            return
        self._after_tasks.append((root, after_id))

    def register_stop_event(self, ev: Any) -> None:
        """
        threading.Event のような stop シグナルを登録する。
        shutdown() で ev.set() を呼ぶ。
        """
        if ev is None:
            return
        self._stop_events.append(ev)

    def register_thread(self, th: Optional[threading.Thread]) -> None:
        """
        join 対象の thread を登録する。
        """
        if th is None:
            return
        self._threads.append(th)

    def register_closeable(self, obj: Any) -> None:
        """
        serialなど close()/stop()/shutdown() を持つ可能性があるオブジェクトを登録する。
        shutdown() で利用可能なメソッドを順に呼ぶ（存在するものだけ）。
        """
        if obj is None:
            return
        self._closeables.append(obj)

    def register_callback(self, fn: Optional[Callable[[], None]]) -> None:
        """
        明示的に呼ぶ必要がある停止処理を登録する。
        """
        if fn is None:
            return
        self._callbacks.append(fn)

    def shutdown(
        self,
        root: Any,
        *,
        reason: str = "",
        join_timeout_sec: float = 1.5,
        force_exit: bool = False,
    ) -> None:
        """
        登録済みのリソースを順番に停止し、GUI を終了させる。

        root:
          - Tkinter root（quit/destroy を呼ぶ）

        join_timeout_sec:
          - worker thread の join を待つ最大秒（スレッドが残っても次へ進む）

        force_exit:
          - True の場合、最後に os._exit(0) を実行して “確実に” 終了する
            （通常は False 推奨。問題が残る環境のみ最終手段として使用）
        """
        with self._lock:
            if self._started:
                logger.warning("Shutdown already started; ignore duplicate call. reason=%s", reason)
                return
            self._started = True

        logger.info("Shutdown sequence started. reason=%s", reason)

        # 1) after() を止める（タイマーが残ると終了を阻害する）
        for r, task_id in list(self._after_tasks):
            try:
                r.after_cancel(task_id)
            except Exception:
                # 既にキャンセル済み / root破棄済み等
                logger.debug("after_cancel failed (ignored): %s", task_id, exc_info=True)

        # 2) stop event を set（スレッド/ループに止まる合図）
        for ev in list(self._stop_events):
            try:
                if hasattr(ev, "set"):
                    ev.set()
            except Exception:
                logger.debug("stop_event.set() failed (ignored)", exc_info=True)

        # 3) 明示停止コールバック（tray停止など、順序を先に）
        for fn in list(self._callbacks):
            try:
                fn()
            except Exception:
                logger.debug("shutdown callback failed (ignored)", exc_info=True)

        # 4) closeable を閉じる（serialなど）
        for obj in list(self._closeables):
            try:
                # close / stop / shutdown の順で試す（存在するものだけ）
                if hasattr(obj, "close") and callable(getattr(obj, "close")):
                    obj.close()
                elif hasattr(obj, "stop") and callable(getattr(obj, "stop")):
                    obj.stop()
                elif hasattr(obj, "shutdown") and callable(getattr(obj, "shutdown")):
                    obj.shutdown()
            except Exception:
                logger.debug("closeable stop failed (ignored)", exc_info=True)

        # 5) thread を join（短時間だけ待つ）
        deadline = time.monotonic() + max(0.1, join_timeout_sec)
        for th in list(self._threads):
            try:
                if th.is_alive():
                    remaining = max(0.0, deadline - time.monotonic())
                    th.join(timeout=remaining)
            except Exception:
                logger.debug("thread.join failed (ignored)", exc_info=True)

        # 6) Tk 終了（quit→destroy）
        try:
            if root is not None:
                try:
                    root.quit()
                except Exception:
                    logger.debug("root.quit failed (ignored)", exc_info=True)
                try:
                    root.destroy()
                except Exception:
                    logger.debug("root.destroy failed (ignored)", exc_info=True)
        finally:
            logger.info("Shutdown sequence finished. reason=%s force_exit=%s", reason, force_exit)

        # 7) 最終手段：強制終了
        if force_exit:
            os._exit(0)