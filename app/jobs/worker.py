"""
Asynchronous Job Worker and Execution Orchestrator (Section 19 of architecture).
"""
import asyncio
import json
import traceback
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.storage.database import AsyncSessionLocal


class JobManager:
    """
    Manages asynchronous job lifecycle: QUEUED -> RUNNING -> COMPLETED / FAILED.
    Provides non-blocking execution with database-persisted states.
    """

    async def create_job(
        self, db: AsyncSession, job_type: str, input_params: Dict[str, Any]
    ) -> Job:
        job_id = f"JOB_{uuid.uuid4().hex[:12].upper()}"
        job = Job(
            job_id=job_id,
            job_type=job_type,
            status="QUEUED",
            progress_pct=0.0,
            input_params_json=json.dumps(input_params),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job

    async def get_job(self, db: AsyncSession, job_id: str) -> Optional[Job]:
        stmt = select(Job).where(Job.job_id == job_id)
        res = await db.execute(stmt)
        return res.scalar_one_or_none()

    def dispatch_job(self, job_id: str, task_fn: Callable, *args, **kwargs) -> None:
        """Schedules asynchronous task execution without blocking API request."""
        asyncio.create_task(self._run_job_wrapper(job_id, task_fn, *args, **kwargs))

    async def _run_job_wrapper(self, job_id: str, task_fn: Callable, *args, **kwargs) -> None:
        # Step 1: Mark job as RUNNING
        async with AsyncSessionLocal() as session:
            stmt = select(Job).where(Job.job_id == job_id)
            res = await session.execute(stmt)
            job = res.scalar_one_or_none()
            if not job:
                return
            job.status = "RUNNING"
            job.started_at = datetime.now(timezone.utc)
            await session.commit()

        # Step 2: Progress callback closure
        async def update_progress(pct: float):
            async with AsyncSessionLocal() as sess:
                s = select(Job).where(Job.job_id == job_id)
                r = await sess.execute(s)
                j = r.scalar_one_or_none()
                if j:
                    j.progress_pct = pct
                    await sess.commit()

        # Step 3: Run the task function
        try:
            async with AsyncSessionLocal() as run_session:
                result = await task_fn(run_session, *args, progress_callback=update_progress, **kwargs)

            # Step 4: Mark COMPLETED
            async with AsyncSessionLocal() as sess:
                s = select(Job).where(Job.job_id == job_id)
                r = await sess.execute(s)
                j = r.scalar_one_or_none()
                if j:
                    j.status = "COMPLETED"
                    j.progress_pct = 100.0
                    j.result_summary_json = json.dumps(result)
                    j.completed_at = datetime.now(timezone.utc)
                    await sess.commit()

        except Exception as exc:
            # Step 5: Mark FAILED with error trace
            err_details = {
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
                "traceback": traceback.format_exc(),
            }
            async with AsyncSessionLocal() as sess:
                s = select(Job).where(Job.job_id == job_id)
                r = await sess.execute(s)
                j = r.scalar_one_or_none()
                if j:
                    j.status = "FAILED"
                    j.error_details_json = json.dumps(err_details)
                    j.completed_at = datetime.now(timezone.utc)
                    await sess.commit()


job_manager = JobManager()
