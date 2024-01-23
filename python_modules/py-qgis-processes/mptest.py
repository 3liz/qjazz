import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor
import os
import time
import asyncio

def hello(p,name: str) -> str:
    time.sleep(1)
    print(f"Hello from {name}: {os.getpid()} ppid: {os.getppid()}")
    p.send(f"ok {name}")

def run_in_process(*args):
   parent, child = mp.Pipe(duplex=True)  
   p = mp.Process(target=hello, args=(child, *args))
   p.start()
   p.join()
   return parent.recv()

async def main():
    loop = asyncio.get_running_loop()
    print("ppid:", os.getpid())
    with ThreadPoolExecutor(max_workers=2) as pool:
        done = await asyncio.gather(
            loop.run_in_executor(pool, run_in_process, f"task1"),
            loop.run_in_executor(pool, run_in_process, f"task2"),
            loop.run_in_executor(pool, run_in_process, f"task3"),
        )
        print(done)

if __name__ == '__main__':
    mp.set_start_method('forkserver')
    asyncio.run(main())
