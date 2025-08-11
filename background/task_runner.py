"""
백그라운드 태스크 실행 모듈
별도 스레드와 이벤트 루프에서 비동기 작업 실행
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Coroutine, Any, Optional
import logging

logger = logging.getLogger(__name__)


class BackgroundTaskRunner:
    """
    백그라운드 태스크 실행기
    FastAPI의 메인 이벤트 루프를 블로킹하지 않고 비동기 작업 실행
    """
    
    def __init__(self, max_workers: int = 4):
        """
        Args:
            max_workers: 동시 실행 가능한 최대 워커 수
        """
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="bg_task_"
        )
        self._running_tasks = []
        logger.info(f"BackgroundTaskRunner initialized with {max_workers} workers")
    
    def run_async_task(self, coro: Coroutine[Any, Any, Any]) -> Future:
        """
        별도 스레드의 새로운 이벤트 루프에서 비동기 태스크 실행
        
        Args:
            coro: 실행할 코루틴
            
        Returns:
            Future 객체 (결과 확인용)
        """
        def run_in_new_loop():
            """새로운 이벤트 루프를 생성하고 코루틴 실행"""
            # 새로운 이벤트 루프 생성
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # 코루틴 실행
                result = loop.run_until_complete(coro)
                logger.info(f"Background task completed in thread {threading.current_thread().name}")
                return result
            except Exception as e:
                logger.error(f"Background task failed in thread {threading.current_thread().name}: {str(e)}")
                raise
            finally:
                # 이벤트 루프 정리
                try:
                    loop.close()
                except Exception as e:
                    logger.warning(f"Error closing event loop: {str(e)}")
        
        # ThreadPoolExecutor에서 실행
        future = self.executor.submit(run_in_new_loop)
        self._running_tasks.append(future)
        
        # 완료된 태스크 정리
        self._cleanup_completed_tasks()
        
        logger.info(f"Background task submitted. Active tasks: {len(self._running_tasks)}")
        return future
    
    def _cleanup_completed_tasks(self):
        """완료된 태스크를 리스트에서 제거"""
        self._running_tasks = [
            task for task in self._running_tasks 
            if not task.done()
        ]
    
    def shutdown(self, wait: bool = True):
        """
        실행기 종료
        
        Args:
            wait: 진행 중인 태스크가 완료될 때까지 대기할지 여부
        """
        logger.info(f"Shutting down BackgroundTaskRunner (wait={wait})")
        self.executor.shutdown(wait=wait)
    
    def get_active_task_count(self) -> int:
        """현재 실행 중인 태스크 수 반환"""
        self._cleanup_completed_tasks()
        return len(self._running_tasks)
    
    def wait_all(self, timeout: Optional[float] = None):
        """
        모든 태스크가 완료될 때까지 대기
        
        Args:
            timeout: 최대 대기 시간 (초)
        """
        from concurrent.futures import wait, FIRST_COMPLETED
        
        if not self._running_tasks:
            return
        
        logger.info(f"Waiting for {len(self._running_tasks)} tasks to complete")
        done, not_done = wait(self._running_tasks, timeout=timeout)
        
        if not_done:
            logger.warning(f"{len(not_done)} tasks did not complete within timeout")
        
        # 완료된 태스크 정리
        self._cleanup_completed_tasks()


# 싱글톤 인스턴스
_task_runner: Optional[BackgroundTaskRunner] = None


def get_task_runner() -> BackgroundTaskRunner:
    """싱글톤 태스크 러너 반환"""
    global _task_runner
    if _task_runner is None:
        _task_runner = BackgroundTaskRunner(max_workers=4)
    return _task_runner


def run_in_background(coro: Coroutine[Any, Any, Any]) -> Future:
    """
    편의 함수: 백그라운드에서 코루틴 실행
    
    Args:
        coro: 실행할 코루틴
        
    Returns:
        Future 객체
        
    Example:
        >>> async def my_task():
        ...     await asyncio.sleep(1)
        ...     return "done"
        >>> future = run_in_background(my_task())
    """
    return get_task_runner().run_async_task(coro)