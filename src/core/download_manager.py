"""Download manager for coordinating multiple download tasks."""
from typing import Dict, List, Optional
from pathlib import Path
from PySide6.QtCore import QObject, Signal

from ..config.settings import AppSettings
from ..config.constants import STATUS_QUEUED, STATUS_DOWNLOADING, STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED
from ..utils.logger import logger
from .download_worker import DownloadWorker, DownloadTask
from .rate_limit import RateLimitCoordinator


class DownloadManager(QObject):
    """Manages download queue and coordinates worker threads."""
    
    # Signals
    task_added = Signal(DownloadTask)
    task_updated = Signal(DownloadTask)
    task_completed = Signal(DownloadTask)
    task_failed = Signal(DownloadTask)
    queue_changed = Signal()
    
    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._tasks: Dict[int, DownloadTask] = {}
        self._workers: Dict[int, DownloadWorker] = {}
        self._rate_limit_coordinator = RateLimitCoordinator()
        self._remove_when_finished: set[int] = set()
        self._next_task_id = 1
    
    def add_task(self, url: str) -> DownloadTask:
        """Add a new download task to the queue."""
        task = DownloadTask(
            id=self._next_task_id,
            url=url,
            output_dir=str(Path(self.settings.output_dir).expanduser().resolve()),
            status=STATUS_QUEUED
        )
        self._next_task_id += 1
        
        self._tasks[task.id] = task
        logger.info(f"Added task {task.id}: {url}")
        
        self.task_added.emit(task)
        self.queue_changed.emit()
        
        # Try to start the task immediately if slots are available
        self._try_start_next_task()
        
        return task
    
    def add_tasks(self, urls: List[str]) -> List[DownloadTask]:
        """Add multiple download tasks."""
        tasks = []
        for url in urls:
            task = self.add_task(url)
            tasks.append(task)
        return tasks

    def add_completed_task(self, url: str, output_file: str, title: str = "") -> DownloadTask:
        """Add a playlist item already present in the destination as completed."""
        task = DownloadTask(
            id=self._next_task_id,
            url=url,
            output_dir=str(Path(self.settings.output_dir).expanduser().resolve()),
            status=STATUS_COMPLETED,
            progress=100,
            output_file=output_file,
            error_message="Already present and validated",
            title=title,
        )
        self._next_task_id += 1
        self._tasks[task.id] = task
        self.task_added.emit(task)
        self.task_completed.emit(task)
        self.queue_changed.emit()
        return task
    
    def cancel_task(self, task_id: int) -> bool:
        """Cancel a specific task."""
        if task_id in self._workers:
            worker = self._workers[task_id]
            worker.cancel()
            return True
        elif task_id in self._tasks:
            # Task is queued but not started yet
            task = self._tasks[task_id]
            task.status = STATUS_CANCELLED
            self.task_updated.emit(task)
            self.queue_changed.emit()
            return True
        return False

    def retry_task(self, task_id: int) -> bool:
        """Requeue a failed task while preserving its ID and queue row."""
        task = self._tasks.get(task_id)
        if not task or task.status != STATUS_FAILED or task_id in self._workers:
            return False

        task.status = STATUS_QUEUED
        task.progress = 0
        task.speed = ""
        task.eta = ""
        task.output_file = None
        task.error_message = None
        self.task_updated.emit(task)
        self.queue_changed.emit()
        self._try_start_next_task()
        return True
    
    def cancel_all(self) -> None:
        """Cancel all active and queued tasks."""
        logger.info("Cancelling all tasks")
        
        # Cancel running workers
        for worker in list(self._workers.values()):
            worker.cancel()
        
        # Update queued tasks
        for task in self._tasks.values():
            if task.status == STATUS_QUEUED:
                task.status = STATUS_CANCELLED
                self.task_updated.emit(task)
        
        self.queue_changed.emit()
    
    def clear_completed(self) -> None:
        """Remove completed tasks from the queue."""
        to_remove = [
            task_id for task_id, task in self._tasks.items()
            if task.status == STATUS_COMPLETED
        ]
        for task_id in to_remove:
            del self._tasks[task_id]
        
        if to_remove:
            logger.info(f"Cleared {len(to_remove)} completed tasks")
            self.queue_changed.emit()
    
    def clear_failed(self) -> None:
        """Remove failed tasks from the queue."""
        to_remove = [
            task_id for task_id, task in self._tasks.items()
            if task.status == STATUS_FAILED
        ]
        for task_id in to_remove:
            del self._tasks[task_id]
        
        if to_remove:
            logger.info(f"Cleared {len(to_remove)} failed tasks")
            self.queue_changed.emit()
    
    def clear_all(self) -> None:
        """Cancel active work and remove every task that has no live worker."""
        self.cancel_all()
        active_ids = set(self._workers)
        self._remove_when_finished.update(active_ids)
        self._tasks = {task_id: task for task_id, task in self._tasks.items() if task_id in active_ids}
        logger.info("Cleared all tasks")
        self.queue_changed.emit()
    
    def get_task(self, task_id: int) -> Optional[DownloadTask]:
        """Get a task by ID."""
        return self._tasks.get(task_id)
    
    def get_all_tasks(self) -> List[DownloadTask]:
        """Get all tasks."""
        return list(self._tasks.values())
    
    def get_stats(self) -> Dict[str, int]:
        """Get download statistics."""
        stats = {
            'total': len(self._tasks),
            'queued': 0,
            'downloading': 0,
            'completed': 0,
            'failed': 0,
            'cancelled': 0,
        }
        
        for task in self._tasks.values():
            if task.status == STATUS_QUEUED:
                stats['queued'] += 1
            elif task.status == STATUS_DOWNLOADING:
                stats['downloading'] += 1
            elif task.status == STATUS_COMPLETED:
                stats['completed'] += 1
            elif task.status == STATUS_FAILED:
                stats['failed'] += 1
            elif task.status == STATUS_CANCELLED:
                stats['cancelled'] += 1
        
        return stats
    
    def _try_start_next_task(self) -> None:
        """Try to start the next queued task if slots are available."""
        running_count = len(self._workers)
        max_parallel = self.settings.max_parallel_downloads
        
        if running_count >= max_parallel:
            return
        
        # Find next queued task
        for task in self._tasks.values():
            if task.status == STATUS_QUEUED:
                self._start_task(task)
                break
    
    def _start_task(self, task: DownloadTask) -> None:
        """Start downloading a task."""
        if task.id in self._workers:
            return
        
        logger.info(f"Starting task {task.id}")
        task.status = STATUS_DOWNLOADING
        task.progress = 0
        
        # Create worker
        worker = DownloadWorker(
            task,
            self.settings,
            self,
            rate_limit_coordinator=self._rate_limit_coordinator,
        )
        self._workers[task.id] = worker
        
        # Connect signals
        worker.progress_updated.connect(
            lambda progress, speed, eta, t=task: self._on_task_progress(t, progress, speed, eta)
        )
        worker.title_updated.connect(
            lambda title, t=task: self._on_task_title(t, title)
        )
        worker.status_changed.connect(
            lambda message, t=task: self._on_task_status(t, message)
        )
        worker.finished.connect(
            lambda status, output, error, t=task: self._on_task_finished(t, status, output, error)
        )
        
        # Start worker
        worker.start()
        
        self.task_updated.emit(task)
        self.queue_changed.emit()
    
    def _on_task_progress(self, task: DownloadTask, progress: int, speed: str, eta: str) -> None:
        """Handle progress update from worker."""
        task.progress = progress
        task.speed = speed
        task.eta = eta
        self.task_updated.emit(task)

    def _on_task_title(self, task: DownloadTask, title: str) -> None:
        task.title = title
        self.task_updated.emit(task)

    def _on_task_status(self, task: DownloadTask, message: str) -> None:
        task.status_message = (
            message if message.startswith("Waiting for YouTube rate limit cooldown") else ""
        )
        self.task_updated.emit(task)
    
    def _on_task_finished(self, task: DownloadTask, status: str, output_file: str, error_message: str) -> None:
        """Handle task completion."""
        # Clean up worker
        worker = self._workers.pop(task.id, None)
        if worker:
            worker.deleteLater()
        
        # Update task
        task.status = status
        task.status_message = ""
        task.output_file = output_file if output_file else None
        task.error_message = error_message if error_message else None
        
        if status == STATUS_COMPLETED:
            task.progress = 100
            logger.info(f"Task {task.id} completed: {output_file}")
            self.task_completed.emit(task)
        elif status == STATUS_FAILED:
            logger.error(f"Task {task.id} failed: {error_message}")
            self.task_failed.emit(task)
        
        self.task_updated.emit(task)
        self.queue_changed.emit()

        if task.id in self._remove_when_finished:
            self._remove_when_finished.discard(task.id)
            self._tasks.pop(task.id, None)
            self.queue_changed.emit()
            return
        
        # Try to start next task
        self._try_start_next_task()
    
    def start_all_queued(self) -> None:
        """Start all queued tasks (respecting parallel limit)."""
        logger.info("Starting all queued tasks")
        while True:
            running_count = len(self._workers)
            if running_count >= self.settings.max_parallel_downloads:
                break

            # Find next queued task
            next_task = next((task for task in self._tasks.values() if task.status == STATUS_QUEUED), None)
            if next_task:
                self._start_task(next_task)
            else:
                break

    def shutdown(self) -> None:
        """Request cancellation and wait for workers before their owner is destroyed."""
        self.cancel_all()
        for worker in list(self._workers.values()):
            worker.wait()
