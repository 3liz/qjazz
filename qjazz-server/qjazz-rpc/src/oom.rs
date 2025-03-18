//
// Helpers to kill processes if the memory occupied
//
use nix::{sys::signal, unistd::Pid};
use procfs::{process::Process, Current, Meminfo, ProcResult};
use std::error::Error;
use std::sync::Arc;
use tokio::sync::RwLock;
use tokio::task::JoinHandle;
use tokio::time;
use tokio_util::sync::CancellationToken;

use qjazz_pool::Pool;

pub(crate) fn handle_oom(
    pool: Arc<RwLock<Pool>>,
    token: CancellationToken,
    high_water_mark: f64,
    throttle_duration: time::Duration,
) -> Result<JoinHandle<()>, Box<dyn Error>> {
    // RSS is returned in number of memory pages
    // so we need the pagesize from sysconf 
    // NOTE: on linux x64 the page size is 4096
    let pagesize = sysconf::pagesize() as u64;
    let total_mem = Meminfo::current()?.mem_total as f64;

    let handle = tokio::spawn(async move {
        log::info!("Installing oom handler");
        while !token.is_cancelled() {
            time::sleep(throttle_duration).await;
            if token.is_cancelled() {
                break;
            }
            pool.read()
                .await
                .inspect_pids(|pids| {
                    log::trace!("Running oom handler");
                    tokio::task::spawn_blocking(move || {
                        if let Err(error) =
                            kill_out_of_memory_processes(pids, total_mem, pagesize, high_water_mark)
                        {
                            log::error!("Failed to run the oom killer {error}");
                        }
                    });
                })
                .await;
        }
    });
    Ok(handle)
}

pub fn kill_out_of_memory_processes(
    processes: Vec<i32>,
    total_mem: f64,
    pagesize: u64,
    hwm: f64,
) -> ProcResult<()> {
    let this = std::process::id() as i32;

    let mut mem_usage = processes
        .iter()
        .filter_map(|pid| Process::new(*pid).ok())
        .filter_map(|proc| {
            // NOTE: procfs hold the /proc/<pi> directory so that 
            // the pid will not be reused as long as `proc` exists.
            if let Ok(st) = proc.stat() {
                // Consistency check: make sure the process is a child
                // of `this` and is not terminated or zombi
                if st.ppid != this || st.state == 'Z' || st.state == 'X' {
                    return None;
                }
                let memory_percent = (st.rss * pagesize) as f64 / total_mem;
                log::debug!("=Processes memory usage [{}]: {:.6}", proc.pid, memory_percent);
                Some((memory_percent, proc))
            } else {
                None
            }
        })
        .collect::<Vec<_>>();

    let mut memory_fraction = mem_usage.iter().fold(0., |acc, (mem, _)| acc + mem);
    if memory_fraction > hwm {
        log::error!("CRITICAL: high memory water mark reached {memory_fraction}");

        // Sort child processes in descending order
        // kill child processes until memory get low
        mem_usage.sort_by_key(|(mem, _)| (mem * 1000.0).trunc() as i64);
        for (mem, proc) in mem_usage.iter().rev() {
            let pid = Pid::from_raw(proc.pid);
            log::error!("OOM: killing worker: {pid} (mem usage: {mem})");
            if let Err(err) = signal::kill(pid, signal::SIGKILL) {
                log::error!("Failed to kill process {pid}: {err}");
                continue;
            }
            memory_fraction -= mem;
            if memory_fraction < hwm {
                break;
            }
        }
    }

    Ok(())
}
