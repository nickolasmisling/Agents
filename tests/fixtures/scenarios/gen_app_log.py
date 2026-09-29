#!/usr/bin/env python3
"""Generate sample-app/logs/app.log deterministically.

Usage: python3 gen_app_log.py [output_path]

Two hours of batchtrack API logs around the 1.4.0 -> 1.4.1 deploy. The seeded
incident (LOG-01 .. LOG-08) is described in answer-key/data-and-history.md.
"""

import os
import random
import sys
from datetime import datetime, timedelta, timezone

SEED = 4521
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "..", "sample-app", "logs", "app.log")

START = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 9, 14, 14, 0, 0, tzinfo=timezone.utc)
DEPLOY_STOP = START + timedelta(hours=1, minutes=11, seconds=58.402)
DEPLOY_UP = START + timedelta(hours=1, minutes=12, seconds=9.850)
WARMER_FIRST = START + timedelta(hours=1, minutes=13, seconds=10.012)
FIRST_LOCK = START + timedelta(hours=1, minutes=18, seconds=27.531)

USERS = ["jgomez", "lmartinez", "aperez", "dcastro", "mhernandez", "rsuarez",
         "pvargas", "ngarcia", "ctorres", "jramirez", "sortiz", "emoreno"]
SITES = ["BOG", "BAQ", "CLO", "MDE"]

rng = random.Random(SEED)
events = []
warmer_runs = []


def ts(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def emit(t, level, logger, msg, extra=()):
    events.append((t, len(events), f"{ts(t)} {level:<5} [{logger}] {msg}", list(extra)))


def rid():
    return f"{rng.getrandbits(32):08x}"


def request_line(t, degraded):
    batch_id = rng.randint(1690, 1843)
    user = rng.choice(USERS)
    roll = rng.random()
    if roll < 0.30:
        method, path = "GET", f"/batches?site={rng.choice(SITES)}&status=released&page={rng.randint(1, 4)}"
    elif roll < 0.55:
        method, path = "GET", f"/batches/{batch_id}"
    elif roll < 0.68:
        method, path = "GET", f"/batches/{batch_id}/signatures"
    elif roll < 0.80:
        method, path = "GET", "/dashboard/summary"
    elif roll < 0.90:
        method, path = "POST", f"/batches/{batch_id}/signatures"
    else:
        method, path = "POST", "/batches"
    base = rng.lognormvariate(3.6, 0.45) if method == "GET" else rng.lognormvariate(4.1, 0.4)
    duration = int(base * (1 + degraded * rng.uniform(4, 30)))
    status = 201 if method == "POST" else 200
    emit(t, "INFO", "batchtrack.api",
         f"req={rid()} method={method} path={path} status={status} duration_ms={duration} user={user}")


def degradation(t):
    """0 before the warmer starts contending, rising to ~1 twenty minutes later."""
    if t < WARMER_FIRST:
        return 0.0
    minutes = (t - WARMER_FIRST).total_seconds() / 60.0
    return min(1.0, max(0.0, (minutes - 2.5) / 12.0))


def baseline_noise():
    t = START
    while t < END:
        minute_end = t + timedelta(minutes=1)
        for _ in range(rng.choice([0, 1, 1, 1, 2])):
            at = t + timedelta(seconds=rng.uniform(0.5, 59.5))
            if DEPLOY_STOP <= at <= DEPLOY_UP + timedelta(seconds=1):
                continue
            request_line(at, degradation(at))
        if rng.random() < 0.10:
            at = t + timedelta(seconds=rng.uniform(1, 59))
            emit(at, "WARN", "batchtrack.lims",
                 f"deprecated endpoint in use endpoint=/api/v2/samples sunset=2026-12-31 "
                 f"lot={rng.choice(['API-PCM-2601', 'OIL-OM3-2603', 'GEL-BOV-2605', 'API-IBU-2602'])}")
        if int((t - START).total_seconds() // 60) in (7, 26, 41, 58, 83, 97, 109):
            at = t + timedelta(seconds=rng.uniform(1, 59))
            emit(at, "WARN", "batchtrack.auth",
                 f"login failed username={rng.choice(USERS)} reason=bad_password remote=10.20.{rng.randint(1, 9)}.{rng.randint(10, 250)}")
        if rng.random() < 0.05:
            at = t + timedelta(seconds=rng.uniform(1, 59))
            emit(at, "WARN", "batchtrack.lims",
                 f"slow response endpoint=/api/v2/samples duration_ms={rng.randint(2100, 3400)}")
        if t.minute in (22, 47):
            at = t + timedelta(seconds=rng.uniform(1, 59))
            emit(at, "WARN", "batchtrack.api",
                 f"slow request req={rid()} method=GET path=/reports/site-yield duration_ms={rng.randint(2900, 3600)} user={rng.choice(USERS)}")
        t = minute_end


def scheduled_jobs():
    run = 407
    t = START + timedelta(seconds=0.214)
    while t < END:
        if DEPLOY_STOP <= t <= DEPLOY_UP:
            t += timedelta(minutes=15)
            continue
        run += 1
        emit(t, "INFO", "batchtrack.jobs", f"job=audit_export run_id=ae-{run:04d} started")
        emit(t + timedelta(seconds=0.35), "WARN", "py.warnings",
             "/opt/batchtrack/app/audit_export.py:41: DeprecationWarning: datetime.datetime.utcnow() is "
             "deprecated and scheduled for removal in a future version. Use timezone-aware objects to "
             "represent datetimes in UTC: datetime.datetime.now(datetime.UTC).")
        rows = rng.randint(18, 64)
        emit(t + timedelta(seconds=rng.uniform(0.6, 1.4)), "INFO", "batchtrack.jobs",
             f"job=audit_export run_id=ae-{run:04d} finished rows={rows} duration_ms={rng.randint(640, 1310)}")
        t += timedelta(minutes=15)
    for minute in (0, 30, 60, 90):
        at = START + timedelta(minutes=minute, seconds=5.0 + rng.random())
        emit(at, "WARN", "batchtrack.disk", f"volume /var/lib/batchtrack usage={81 + minute // 60}% threshold=80%")


def deploy():
    emit(DEPLOY_STOP, "INFO", "batchtrack.server", "received SIGTERM, draining connections version=1.4.0 pid=2281")
    emit(DEPLOY_STOP + timedelta(seconds=4.715), "INFO", "batchtrack.server", "stopped version=1.4.0 pid=2281 uptime_s=431877")
    t = DEPLOY_UP
    emit(t, "INFO", "batchtrack.server", "starting batchtrack version=1.4.1 commit=8e1d2c7 python=3.11.9 pid=3117")
    emit(t + timedelta(seconds=0.061), "INFO", "batchtrack.config",
         "db=/var/lib/batchtrack/batchtrack.db db_pool_size=10 db_pool_timeout_s=5.0 sqlite_busy_timeout_ms=5000 "
         "journal_mode=delete access_log_sample=0.05")
    emit(t + timedelta(seconds=0.153), "INFO", "batchtrack.jobs", "scheduled job=audit_export every=900s")
    emit(t + timedelta(seconds=0.155), "INFO", "batchtrack.jobs", "scheduled job=cache_warmer every=120s workers=8 scope=all_batches")
    emit(t + timedelta(seconds=0.371), "INFO", "batchtrack.server", "listening on 0.0.0.0:8080 threads=16")
    emit(t + timedelta(seconds=4.650), "INFO", "batchtrack.deploy",
         "deploy finished release=1.4.1 previous=1.4.0 change=CHG-20931 actor=ci-release")


WARMER_TRACE = """Traceback (most recent call last):
  File "/opt/batchtrack/app/scheduler.py", line 58, in _run_job
    job.func(**job.kwargs)
  File "/opt/batchtrack/app/cache.py", line 45, in warm_cache
    for _ in pool.map(lambda batch_no: get_batch(db_path, batch_no), batch_numbers):
  File "/usr/lib/python3.11/concurrent/futures/_base.py", line 619, in result_iterator
    yield _result_or_cancel(fs.pop())
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.11/concurrent/futures/_base.py", line 317, in _result_or_cancel
    return fut.result(timeout)
           ^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.11/concurrent/futures/_base.py", line 456, in result
    return self.__get_result()
           ^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.11/concurrent/futures/_base.py", line 401, in __get_result
    raise self._exception
  File "/usr/lib/python3.11/concurrent/futures/thread.py", line 58, in run
    result = self.fn(*self.args, **self.kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/batchtrack/app/cache.py", line 45, in <lambda>
    for _ in pool.map(lambda batch_no: get_batch(db_path, batch_no), batch_numbers):
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/batchtrack/app/cache.py", line 32, in get_batch
    value = _load(db_path, batch_no)
            ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/batchtrack/app/cache.py", line 18, in _load
    row = conn.execute("SELECT * FROM batches WHERE batch_no = ?", (batch_no,)).fetchone()
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
sqlite3.OperationalError: database is locked""".splitlines()

API_TRACE = """Traceback (most recent call last):
  File "/opt/batchtrack/app/api.py", line 82, in do_POST
    sig_id = signatures.sign_batch(
             ^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/batchtrack/app/signatures.py", line 26, in sign_batch
    conn.commit()
sqlite3.OperationalError: database is locked""".splitlines()


def cache_warmer():
    """Runs every 120s; each run gets slower as runs overlap and hold pool connections."""
    durations = [41.3, 63.8, 97.2, 131.5, 158.9, 187.4, 214.0, 236.6]
    active = []
    t = WARMER_FIRST
    run = 0
    traced = False
    while t < END:
        run += 1
        active = [end for end in active if end > t]
        duration = durations[run - 1] if run <= len(durations) else rng.uniform(228.0, 291.0)
        run_id = f"cw-{run:04d}"
        emit(t + timedelta(milliseconds=3), "INFO", "batchtrack.jobs",
             f"job=cache_warmer run_id={run_id} started batches=1843 workers=8 active_runs={len(active) + 1}")
        end = t + timedelta(seconds=duration)
        active.append(end)
        warmer_runs.append((t, end))
        if end < END:
            if run <= 4 or (run > 6 and rng.random() < 0.3):
                emit(end, "INFO", "batchtrack.jobs",
                     f"job=cache_warmer run_id={run_id} finished loaded=1843 duration_ms={int(duration * 1000)} "
                     f"cache_size=1843 hit_rate={0.0 if run == 1 else round(rng.uniform(0.05, 0.2), 3)}")
            elif not traced:
                traced = True
                emit(end, "ERROR", "batchtrack.jobs",
                     f"job=cache_warmer run_id={run_id} failed duration_ms={int(duration * 1000)} loaded={rng.randint(900, 1400)}/1843",
                     WARMER_TRACE)
            else:
                emit(end, "ERROR", "batchtrack.jobs",
                     f"job=cache_warmer run_id={run_id} failed duration_ms={int(duration * 1000)} "
                     f"loaded={rng.randint(700, 1500)}/1843 error=\"sqlite3.OperationalError: database is locked\"")
        t += timedelta(seconds=120, milliseconds=rng.randint(0, 40))


error_counts = {}


def errors_per_minute(minute_start):
    if minute_start + timedelta(minutes=1) <= FIRST_LOCK:
        return 0
    if minute_start not in error_counts:
        minutes = max((minute_start - FIRST_LOCK).total_seconds() / 60.0, 0)
        ramp = int(1.6 * minutes ** 1.25 + rng.uniform(0, 3))
        error_counts[minute_start] = max(1, min(ramp, rng.randint(24, 34)))
    return error_counts[minute_start]


def incident_errors():
    t = FIRST_LOCK.replace(second=0, microsecond=0)
    first = True
    pool_first = FIRST_LOCK + timedelta(seconds=74.2)
    while t < END:
        n = errors_per_minute(t)
        shown = 0
        for i in range(n):
            at = max(t, FIRST_LOCK) + timedelta(seconds=rng.uniform(0, 59.9 - max(0, (FIRST_LOCK - t).total_seconds())))
            if first:
                at = FIRST_LOCK
            batch_id = rng.randint(1690, 1843)
            if at >= pool_first and rng.random() < 0.55:
                msg = (f"req={rid()} method={rng.choice(['GET', 'GET', 'POST'])} path=/batches/{batch_id} status=503 "
                       f"duration_ms={rng.randint(5001, 5019)} error=\"PoolTimeout: no connection available within 5.0s\"")
            else:
                path = rng.choice([f"/batches/{batch_id}/signatures", "/batches", f"/batches/{batch_id}/signatures"])
                msg = (f"req={rid()} method=POST path={path} status=500 duration_ms={rng.randint(5002, 5040)} "
                       f"error=\"sqlite3.OperationalError: database is locked\"")
            if shown < 2 or first:
                emit(at, "ERROR", "batchtrack.api", msg, API_TRACE if first else ())
                shown += 1
            first = False
        if n > shown:
            emit(t + timedelta(seconds=59.95), "WARN", "batchtrack.logging",
                 f"suppressed {n - shown} similar messages logger=batchtrack.api in last 60s")
        if t + timedelta(minutes=1) > pool_first and (t <= pool_first or rng.random() < 0.45):
            waiting = min(14, 1 + int((t - pool_first).total_seconds() / 150))
            at = t + timedelta(seconds=rng.uniform(5, 50))
            running = [(start, n) for n, (start, end) in enumerate(warmer_runs) if start <= at < end]
            start, pool_no = min(running) if running else (at - timedelta(seconds=30), len(warmer_runs))
            held = int((at - start).total_seconds() * 1000) - rng.randint(200, 1500)
            emit(at, "WARN", "batchtrack.db",
                 f"connection pool exhausted size=10 in_use=10 waiting={waiting} "
                 f"oldest_holder=ThreadPoolExecutor-{pool_no + 2}_{rng.randint(0, 7)} held_ms={held}")
        t += timedelta(minutes=1)


def metrics():
    t = START
    while t < END:
        at = t + timedelta(milliseconds=rng.randint(1, 30))
        if DEPLOY_STOP <= at <= DEPLOY_UP + timedelta(seconds=30):
            t += timedelta(minutes=1)
            continue
        d = degradation(at)
        warm = at >= WARMER_FIRST
        p95 = int(rng.uniform(120, 185) * (1 + d * 27))
        p95 = min(p95, rng.randint(5010, 5090))
        p50 = int(rng.uniform(32, 45) * (1 + d * 6))
        p99 = min(int(p95 * rng.uniform(1.4, 2.0)), 5000 + rng.randint(20, 140))
        in_use = rng.randint(1, 3) if not warm else min(10, rng.randint(6, 9) + int(d * 4))
        errs = error_counts.get(t - timedelta(minutes=1), 0)
        requests = rng.randint(38, 61)
        emit(at, "INFO", "batchtrack.metrics",
             f"window=60s requests={requests} errors_5xx={errs} p50_ms={p50} p95_ms={p95} p99_ms={p99} "
             f"db_pool_in_use={in_use}/10")
        t += timedelta(minutes=1)


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    baseline_noise()
    scheduled_jobs()
    deploy()
    cache_warmer()
    incident_errors()
    metrics()
    events.sort(key=lambda e: (e[0], e[1]))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    lines = 0
    with open(out_path, "w", encoding="utf-8") as fh:
        for _, _, line, extra in events:
            fh.write(line + "\n")
            lines += 1
            for cont in extra:
                fh.write(cont + "\n")
                lines += 1
    print(f"wrote {lines} lines to {os.path.normpath(out_path)}")


if __name__ == "__main__":
    main()
