"""
데이터베이스 연결 및 유틸리티 함수
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from sqlmodel import SQLModel, Session, create_engine, select
from dotenv import load_dotenv
import logging

from models import Job, JobEvent, JobStatus

# 환경 변수 로드
load_dotenv(dotenv_path=Path(__file__).with_name(".env"))

logger = logging.getLogger(__name__)

# 데이터베이스 설정
DB_PATH = Path(__file__).with_name("jobs.db")
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)


def init_db():
    """데이터베이스 초기화"""
    SQLModel.metadata.create_all(engine)
    logger.info(f"Database initialized at {DB_PATH}")


def get_session() -> Session:
    """데이터베이스 세션 생성"""
    return Session(engine)


def now_utc() -> datetime:
    """현재 UTC 시간 반환"""
    return datetime.now(timezone.utc)


def record_event(job_id: str, name: str):
    """작업 이벤트 기록"""
    with get_session() as s:
        s.add(JobEvent(job_id=job_id, name=name, at=now_utc()))
        job = s.exec(select(Job).where(Job.id == job_id)).first()
        if job:
            job.updated_at = now_utc()
            s.add(job)
        s.commit()
        logger.debug(f"Event recorded: {job_id} - {name}")


def set_status(job_id: str, status: JobStatus, error: Optional[str] = None):
    """작업 상태 업데이트"""
    with get_session() as s:
        job = s.exec(select(Job).where(Job.id == job_id)).first()
        if job:
            job.status = status
            job.updated_at = now_utc()
            if error:
                job.error = error
            s.add(job)
            s.add(JobEvent(job_id=job_id, name=status, at=now_utc()))
            s.commit()
            logger.info(f"Status updated: {job_id} -> {status}")
        else:
            logger.warning(f"Job not found: {job_id}")


def get_job(job_id: str) -> Optional[Job]:
    """작업 조회"""
    with get_session() as s:
        return s.exec(select(Job).where(Job.id == job_id)).first()


def get_job_events(job_id: str) -> list:
    """작업 이벤트 목록 조회"""
    with get_session() as s:
        return s.exec(
            select(JobEvent)
            .where(JobEvent.job_id == job_id)
            .order_by(JobEvent.at)
        ).all()


def create_job(job: Job) -> Job:
    """새 작업 생성"""
    with get_session() as s:
        s.add(job)
        s.add(JobEvent(job_id=job.id, name="queued", at=now_utc()))
        s.commit()
        s.refresh(job)
        logger.info(f"Job created: {job.id}")
        return job


def update_webhook_status(job_id: str, status: str):
    """웹훅 상태 업데이트"""
    with get_session() as s:
        job = s.exec(select(Job).where(Job.id == job_id)).first()
        if job:
            job.webhook_status = status
            job.updated_at = now_utc()
            s.add(job)
            s.commit()
            logger.info(f"Webhook status updated: {job_id} -> {status}")