import asyncio  # noqa

from contextlib import asynccontextmanager


from py_qgis_rpc.pool import WorkerPool
from py_qgis_rpc.config import ProjectsConfig, QgisConfig, WorkerConfig

pytest_plugins = ('pytest_asyncio',)


def worker_config(projects: ProjectsConfig, num_processes: int) -> WorkerConfig:
    return WorkerConfig(
        name="TestPool",
        qgis=QgisConfig(projects=projects),
        num_processes=num_processes,
    )


@asynccontextmanager
async def pool_context(projects: ProjectsConfig, num_processes: int = 3):
    pool = WorkerPool(worker_config(projects, num_processes))
    await pool.start()
    try:
        yield pool
    finally:
        await pool.terminate_and_join()


async def test_pool_rescale_workers(projects: ProjectsConfig):
    """ Test rescaling projects
    """
    num_processes = 3
    async with pool_context(projects, num_processes=num_processes) as pool:

        assert pool.worker_failure_pressure <= 0.001

        assert pool.num_workers == num_processes
        assert pool.available_workers == num_processes

        print("test_pool_update_config: Increasing number of processes")
        await pool.update_config(worker_config(projects, num_processes=num_processes + 1))

        assert pool.num_workers == num_processes + 1
        assert pool.available_workers == num_processes + 1

        print("test_pool_update_config: Decreasing number of processes")
        await pool.update_config(worker_config(projects, num_processes=num_processes - 1))

        assert pool.num_workers == num_processes - 1
        assert pool.available_workers == num_processes - 1
