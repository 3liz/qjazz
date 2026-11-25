# Adaptive control of the number of workers

Plan for letting `qjazz-rpc` adjust its number of QGIS workers to the load,
instead of running a fixed `worker.num_processes`.

## Constraints

- **Starting a worker is slow.** A Python/QGIS process start
  (`process_start_timeout` defaults to 5s) plus a replay of the restore cache.
  Scaling up must react early, and a warm minimum of workers must stay up.
- **Memory is the binding constraint, not CPU.** Each worker holds its own
  project cache. The OOM handler (`qjazz-rpc/src/oom.rs`) already kills
  workers on memory pressure; a scaler that ignores memory will fight it.
- **Terminating a worker throws its cache away.** Scaling down too eagerly
  makes requests slower.

## Strategy: target-utilization controller

A background task in `qjazz-rpc`, built like `handle_oom`, wakes up every few
seconds and:

1. **Measures** utilization `busy / num_workers` (`Stats::activity()`) and
   smooths it with an exponential moving average (EWMA).
2. **Computes the target count**:
   `desired = ceil(num_workers × smoothed_utilization / target_utilization)`,
   with `target_utilization` around 0.7 (Little's law: concurrency =
   request rate × service time, plus ~30% headroom).
3. **Corrects for queuing**: if requests are waiting for a worker, or the mean
   wait time over the last interval rises, add workers on top of `desired`.
4. **Applies bounds and hysteresis**:
   - clamp to `min_processes..=max_processes`;
   - scale up as soon as the target exceeds the current count for one or two
     samples;
   - scale down only after a cooldown (minutes), one worker at a time.
5. **Guards memory before growing**: don't add a worker if used memory plus
   the average worker size would exceed a threshold below the OOM high water
   mark.

## Signals

| Signal | Status |
|---|---|
| busy / idle workers | Available: `Pool::stats_raw()` |
| waiting requests (`num_waiters`, `request_pressure`) | **Fixed** (step 1) |
| wait time for a worker | **Done** (step 2): `Pool::wait_stats()` |
| failure pressure | Available, but divided by `num_processes`: must use a fixed reference (`max_processes`) once the count is dynamic |
| worker memory size | Partial: the OOM handler reads RSS of busy workers |

## Steps

1. **[done] Fix `num_waiters`.** `WorkerQueue::recv` released its semaphore
   permit immediately, so the waiter count was always ~0 and
   `max_waiting_requests` was never enforced. Replaced by an atomic counter
   with a RAII guard held across the wait.
2. **[done] Measure wait time.** `WorkerQueue::recv` records how long each
   successful request waited for a worker, as cumulative counters (count,
   total, max). The controller computes the mean over its own sampling
   interval by diffing two snapshots (`WaitStats::mean_since`).
3. **[done] Expose the new signals** in the admin `Stats` RPC. `StatsReply`
   gains `waiting_requests`, and cumulative counters `wait_count`,
   `wait_time_total_us`, `wait_time_max_us` (Prometheus-style: clients
   compute the mean over an interval from two samples, so concurrent
   callers don't interfere). Python stubs regenerated.
4. **Make the count adjustable.** Add `Pool::set_num_processes(n)` bounded by
   `min_processes..=max_processes`, followed by `maintain_pool()`. Compute
   failure pressure against `max_processes` instead of `num_processes`.
5. **Don't hold the pool write lock during `grow()`.** Start the processes
   before taking the lock, so admin/stats calls are not blocked for seconds.
6. **Implement the controller** in `qjazz-rpc`, with configuration:
   `min_processes`, `max_processes`, `target_utilization`, sampling interval,
   scale-down cooldown, memory threshold. Disabled by default
   (`min_processes == max_processes == num_processes`).
7. **Graceful scale down** (optional): retire busy workers at recycle time
   (like the generation / life-cycle checks in `recycle_owned`) instead of
   only removing idle ones.

## Alternative: external scaling

On Kubernetes with fixed memory limits per pod, in-process scaling gains
little since the pod's memory is reserved anyway. Prefer a fixed
`num_processes`, export utilization and wait time (step 3), and let the HPA
scale pods (qjazz-map balances across backends). Both can be combined: a
small in-process range (e.g. 2–4) for short spikes, HPA for sustained load.
