"""Очередь распознавания: задачи выполняются по MAX_CONCURRENT штук, остальные ждут и видят своё место."""
import asyncio
import time
import uuid

from starlette.concurrency import run_in_threadpool

from . import config, llm, pdf, pipeline


class Job:
    def __init__(self, user: str, filename: str, pdf_bytes: bytes):
        self.id = uuid.uuid4().hex
        self.user, self.filename, self.pdf = user, filename, pdf_bytes
        self.status = "queued"          # queued → running → done | error
        self.result = self.error = None
        self.created = time.time()
        self.started = self.finished = None


class JobQueue:
    def __init__(self):
        self.jobs: dict = {}
        self.waiting: list = []        # id задач в порядке очереди
        self._q = None
        self._workers = []

    def start(self):
        self._q = asyncio.Queue()
        self._workers = [asyncio.create_task(self._worker()) for _ in range(max(1, config.MAX_CONCURRENT))]

    def submit(self, user: str, filename: str, pdf_bytes: bytes) -> Job:
        self._purge()
        job = Job(user, filename, pdf_bytes)
        self.jobs[job.id] = job
        self.waiting.append(job.id)
        self._q.put_nowait(job.id)
        return job

    async def _worker(self):
        while True:
            jid = await self._q.get()
            job = self.jobs.get(jid)
            if jid in self.waiting:
                self.waiting.remove(jid)
            if not job:
                continue
            job.status, job.started = "running", time.time()
            try:
                data = await run_in_threadpool(pipeline.recognize, job.pdf)
                meta = data["meta"]
                job.result = {"data": data, "filename": job.filename, "doc_type": meta["doc_type"],
                              "preview": await run_in_threadpool(pdf.preview_b64, job.pdf, meta["rotation"])}
                job.status = "done"
            except llm.LLMError as e:
                job.status, job.error = "error", str(e)
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception("Сбой распознавания %s", job.filename)
                job.status, job.error = "error", f"Внутренняя ошибка: {type(e).__name__}: {e}"
            finally:
                job.finished, job.pdf = time.time(), b""

    def view(self, job: Job) -> dict:
        out = {"id": job.id, "status": job.status}
        if job.status == "queued":
            ahead = self.waiting.index(job.id) if job.id in self.waiting else 0
            running = [j for j in self.jobs.values() if j.status == "running"]
            out.update(position=ahead + 1, ahead=ahead, running=len(running),
                       busy_users=sorted({j.user for j in running}))
        elif job.status == "error":
            out["error"] = job.error
        elif job.status == "done":
            out["result"] = job.result
        return out

    def _purge(self):
        limit = time.time() - config.JOB_TTL_MIN * 60
        for jid in [i for i, j in self.jobs.items() if j.finished and j.finished < limit]:
            del self.jobs[jid]


queue = JobQueue()
