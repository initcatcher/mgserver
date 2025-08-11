"""
비동기 작업 테스트
"""
import asyncio
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import JSONResponse
import time

app = FastAPI()

async def slow_task(task_id: str):
    """느린 작업 시뮬레이션"""
    print(f"Task {task_id} started")
    await asyncio.sleep(5)  # 5초 대기
    print(f"Task {task_id} finished")

@app.post("/test1")
async def test_background_tasks(bg: BackgroundTasks):
    """BackgroundTasks 테스트"""
    task_id = "bg_task"
    bg.add_task(slow_task, task_id)
    return {"message": "Task started with BackgroundTasks", "task_id": task_id}

@app.post("/test2")
async def test_create_task():
    """asyncio.create_task 테스트"""
    task_id = "async_task"
    asyncio.create_task(slow_task(task_id))
    return {"message": "Task started with create_task", "task_id": task_id}

@app.post("/test3")
async def test_sync_blocking():
    """동기 블로킹 테스트"""
    task_id = "sync_task"
    await slow_task(task_id)  # 이것은 블로킹됨
    return {"message": "Task completed synchronously", "task_id": task_id}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)