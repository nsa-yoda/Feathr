"""Explicit async lifecycle supervision and deterministic resource cleanup."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from event_platform.queue import InProcessQueue

LifecycleState = Literal["starting", "running", "draining", "stopped", "failed"]
TaskCriticality = Literal["critical", "restartable", "degradable"]
TaskFactory = Callable[[asyncio.Event], Awaitable[None]]
CloseCallback = Callable[[], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class TaskPolicy:
    """Explicit supervision policy metadata for a named background task."""

    criticality: TaskCriticality = "critical"
    restart_limit: int = 0
    restart_backoff: float = 0.0
    drain_on_shutdown: bool = False

    def __post_init__(self) -> None:
        if self.restart_limit < 0 or self.restart_limit > 10:
            raise ValueError("restart_limit must be between 0 and 10")
        if self.restart_backoff < 0 or self.restart_backoff > 60:
            raise ValueError("restart_backoff must be between 0 and 60")


@dataclass(frozen=True, slots=True)
class LifecycleSnapshot:
    state: LifecycleState
    accepting: bool
    active_tasks: tuple[str, ...]
    queue_depth: int
    failure_type: str | None = None

    def __post_init__(self) -> None:
        if self.queue_depth < 0:
            raise ValueError("queue_depth must be non-negative")
        if any(not name or len(name) > 64 for name in self.active_tasks):
            raise ValueError("active task names are invalid")
        if self.failure_type is not None and (not self.failure_type or len(self.failure_type) > 64):
            raise ValueError("failure_type is invalid")
        if self.state == "stopped" and self.accepting:
            raise ValueError("stopped lifecycle cannot accept work")


class LifecycleSupervisor:
    """Own named background tasks and close resources after a bounded drain."""

    def __init__(
        self,
        queue: InProcessQueue,
        *,
        grace_period: float = 5.0,
        resources: Sequence[tuple[str, CloseCallback]] = (),
        logger: logging.Logger | None = None,
    ) -> None:
        if grace_period < 0:
            raise ValueError("grace_period must be non-negative")
        self.queue = queue
        self.grace_period = grace_period
        self._resources = list(resources)
        self._logger = logger or logging.getLogger("event_platform.lifecycle")
        self._stop_event = asyncio.Event()
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._task_stop_events: dict[str, asyncio.Event] = {}
        self._policies: dict[str, TaskPolicy] = {}
        self._degraded_tasks: dict[str, str] = {}
        self._state: LifecycleState = "starting"
        self._failure_type: str | None = None
        self._shutdown_complete = False
        self._shutdown_lock = asyncio.Lock()
        self._unsafe_tasks: tuple[str, ...] = ()

    @property
    def stop_event(self) -> asyncio.Event:
        return self._stop_event

    @property
    def state(self) -> LifecycleState:
        return self._state

    @property
    def failure_type(self) -> str | None:
        return self._failure_type

    def add_resource(self, name: str, close: CloseCallback) -> None:
        if not name or len(name) > 64:
            raise ValueError("resource name is invalid")
        if self._shutdown_complete:
            raise RuntimeError("lifecycle is already shut down")
        self._resources.append((name, close))

    async def start(
        self,
        factories: Mapping[str, TaskFactory] | None = None,
        *,
        policies: Mapping[str, TaskPolicy] | None = None,
    ) -> None:
        if self._state != "starting":
            raise RuntimeError("lifecycle can only start once")
        factory_items = tuple((factories or {}).items())
        names = [name for name, _ in factory_items]
        if any(not name or len(name) > 64 for name in names):
            raise ValueError("task name is invalid")
        if len(names) != len(set(names)):
            raise ValueError("task name is duplicated")
        configured_policies = dict(policies or {})
        if any(name not in names for name in configured_policies):
            raise ValueError("task policy has no registered task")
        self._policies = {name: configured_policies.get(name, TaskPolicy()) for name in names}
        for name, factory in factory_items:
            self._task_stop_events[name] = asyncio.Event()
            self._tasks[name] = asyncio.create_task(
                self._run_task(name, factory, self._task_stop_events[name]),
                name=f"event-platform:{name}",
            )
        self._state = "running"
        self._logger.info(
            "lifecycle running",
            extra={
                "event": "lifecycle.running",
                "state": self._state,
                "task_policies": {
                    name: policy.criticality for name, policy in self._policies.items()
                },
            },
        )

    def task_healthy(self, name: str) -> bool:
        task = self._tasks.get(name)
        return (
            self._state == "running"
            and task is not None
            and not task.done()
            and name not in self._degraded_tasks
        )

    def task_degraded(self, name: str) -> bool:
        """Whether a degradable task stopped without failing canonical service."""

        return name in self._degraded_tasks

    def has_task(self, name: str) -> bool:
        return name in self._tasks

    def all_tasks_healthy(self) -> bool:
        """Return false when a critical task has terminated unexpectedly."""

        return self._state == "running" and all(
            policy.criticality == "degradable"
            or (not self._tasks[name].done() and name not in self._degraded_tasks)
            for name, policy in self._policies.items()
        )

    def snapshot(self, *, queue_depth: int = 0) -> LifecycleSnapshot:
        active = tuple(sorted(name for name, task in self._tasks.items() if not task.done()))
        return LifecycleSnapshot(
            state=self._state,
            accepting=self.queue.accepting,
            active_tasks=active,
            queue_depth=max(0, queue_depth),
            failure_type=self._failure_type,
        )

    async def wait(self) -> None:
        """Wait for supervised tasks to finish, propagating their terminal error."""

        if self._tasks:
            await asyncio.gather(*self._tasks.values())

    async def request_shutdown(self, reason: str = "lifespan") -> None:
        if self._state in {"draining", "stopped"}:
            return
        safe_reason = (
            reason if reason in {"lifespan", "signal", "startup_failure", "test"} else "unknown"
        )
        self.queue.stop_accepting()
        await self.queue.wake()
        if self._state != "failed":
            self._state = "draining"
        self._stop_event.set()
        for name, policy in self._policies.items():
            if not policy.drain_on_shutdown:
                self._task_stop_events[name].set()
        self._logger.info(
            "lifecycle draining",
            extra={
                "event": "lifecycle.draining",
                "state": self._state,
                "reason_code": safe_reason,
            },
        )

    async def shutdown(self) -> LifecycleSnapshot:
        async with self._shutdown_lock:
            return await self._shutdown()

    async def _shutdown(self) -> LifecycleSnapshot:
        if self._shutdown_complete:
            return await self._snapshot_with_queue()
        drain_started = time.monotonic()
        await self.request_shutdown()
        task_values = tuple(self._tasks.values())
        still_pending: set[asyncio.Task[None]] = set()
        if task_values:
            deadline = time.monotonic() + self.grace_period
            pending = set(task_values)
            while pending and time.monotonic() < deadline:
                stats = await self.queue.stats()
                if stats.depth == 0:
                    self._signal_drain_tasks()
                remaining = max(0.0, deadline - time.monotonic())
                if remaining <= 0:
                    break
                _, pending = await asyncio.wait(
                    pending,
                    timeout=min(0.02, remaining),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if pending and await self._queue_is_drained():
                    self._signal_drain_tasks()
            self._signal_drain_tasks()
            if pending:
                _, pending = await asyncio.wait(pending, timeout=0.05)
            self._observe_tasks(task_values)
            if pending:
                self._logger.warning(
                    "lifecycle drain deadline exceeded",
                    extra={
                        "event": "lifecycle.drain_timeout",
                        "state": self._state,
                        "drain_duration_seconds": round(time.monotonic() - drain_started, 3),
                        "pending_tasks": tuple(
                            sorted(
                                name for name, task in self._tasks.items() if task in pending
                            )
                        ),
                    },
                )
                for task in pending:
                    if not task.done():
                        task.cancel()
                _, still_pending = await asyncio.wait(
                    pending,
                    timeout=max(0.05, min(self.grace_period, 1.0)),
                )
                self._observe_tasks(task_values)
                if still_pending:
                    self._logger.error(
                        "lifecycle task cancellation deadline exceeded",
                        extra={
                            "event": "lifecycle.task_cancel_timeout",
                            "state": self._state,
                            "task_count": len(still_pending),
                        },
                    )
                    self._unsafe_tasks = tuple(
                        sorted(name for name, task in self._tasks.items() if task in still_pending)
                    )
                    self._state = "failed"
        snapshot = await self._snapshot_with_queue()
        self._logger.info(
            "lifecycle queue depth before close",
            extra={
                "event": "lifecycle.queue_depth",
                "state": self._state,
                "queue_depth": snapshot.queue_depth,
                "drain_duration_seconds": round(time.monotonic() - drain_started, 3),
                "incomplete_work": snapshot.queue_depth,
            },
        )
        if self._unsafe_tasks:
            self._logger.error(
                "lifecycle resources left open because tasks remain attached",
                extra={
                    "event": "lifecycle.resources_isolated",
                    "state": self._state,
                    "task_count": len(self._unsafe_tasks),
                },
            )
        else:
            await self._close_resources()
        if self._state != "failed":
            self._state = "stopped"
        self._shutdown_complete = True
        return await self._snapshot_with_queue()

    @staticmethod
    def _observe_tasks(tasks: Sequence[asyncio.Task[None]]) -> None:
        for task in tasks:
            if not task.done():
                continue
            try:
                task.exception()
            except asyncio.CancelledError:
                pass

    async def _snapshot_with_queue(self) -> LifecycleSnapshot:
        stats = await self.queue.stats()
        return self.snapshot(queue_depth=stats.depth)

    async def _close_resources(self) -> None:
        for name, close in self._resources:
            try:
                await close()
            except Exception as error:
                if self._failure_type is None:
                    self._failure_type = "ResourceCloseError"
                self._state = "failed"
                self._logger.error(
                    "lifecycle resource close failed",
                    extra={
                        "event": "lifecycle.resource_close_failed",
                        "resource": name,
                        "error_type": type(error).__name__,
                    },
                )

    async def _run_task(
        self, name: str, factory: TaskFactory, task_stop_event: asyncio.Event
    ) -> None:
        policy = self._policies[name]
        attempts = 0
        while True:
            try:
                await factory(task_stop_event)
                if task_stop_event.is_set() or self._state in {"draining", "stopped"}:
                    return
                error: BaseException = RuntimeError("supervised task exited unexpectedly")
            except asyncio.CancelledError:
                if task_stop_event.is_set() or self._state in {"draining", "stopped"}:
                    return
                error = RuntimeError("supervised task cancelled unexpectedly")
            except Exception as caught:
                error = caught

            if policy.criticality == "degradable":
                self._degraded_tasks[name] = type(error).__name__
                self._logger.error(
                    "degradable lifecycle task stopped",
                    extra={
                        "event": "lifecycle.degraded_task",
                        "task": name,
                        "error_type": type(error).__name__,
                        "state": self._state,
                    },
                )
                return
            if (
                policy.criticality == "restartable"
                and attempts < policy.restart_limit
                and not task_stop_event.is_set()
            ):
                attempts += 1
                if policy.restart_backoff:
                    await asyncio.sleep(policy.restart_backoff)
                continue
            await self._mark_failed(name, error)
            raise error

    def _signal_drain_tasks(self) -> None:
        for name, policy in self._policies.items():
            if policy.drain_on_shutdown:
                self._task_stop_events[name].set()

    async def _queue_is_drained(self) -> bool:
        return (await self.queue.stats()).depth == 0

    async def _mark_failed(self, name: str, error: BaseException) -> None:
        self._state = "failed"
        self._failure_type = type(error).__name__
        self._stop_event.set()
        self.queue.stop_accepting()
        await self.queue.wake()
        self._logger.error(
            "supervised lifecycle task failed",
            extra={
                "event": "lifecycle.supervision_failure",
                "task": name,
                "error_type": type(error).__name__,
                "state": "failed",
            },
        )
