"""Keep a self-hosted Lounge server running on Windows without a console window.

Run it with pythonw.exe (normally from the scheduled task that install-lounge-service.ps1
creates). It starts the configured launcher hidden, inside a Windows job object that

* caps the memory of the server and its Stockfish processes together,
* runs them below normal priority so the rest of the machine stays responsive, and
* kills all of them if this supervisor exits, so nothing is ever orphaned.

The server is restarted with backoff when it exits, and killed and restarted when its
health endpoint stops answering. Only one supervisor runs per configuration.

    pythonw lounge_supervisor.py --config service.json          run (normally via the task)
    python  lounge_supervisor.py --config service.json status   print status.json
    python  lounge_supervisor.py --config service.json restart  ask it to restart the server
    python  lounge_supervisor.py --config service.json stop     stop the server and supervisor

The configuration is a small JSON object; see DEFAULTS. Paths may be relative to it.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path

DEFAULTS = {
    "name": "lounge",  # identifies the instance (mutex, task name)
    "python": sys.executable.replace("pythonw.exe", "python.exe"),
    "launcher": None,  # required: script that starts the server
    "launcher_args": [],
    "workdir": None,  # default: the launcher's directory
    "env": {},  # extra environment for the server
    "health_url": "http://127.0.0.1:8001/api/health",
    # Extra probe headers, e.g. the Host and Tailscale-User-Login that Tailscale Serve
    # sends, for a server in tailscale-serve mode that rejects bare loopback requests.
    "health_headers": {},
    "state_dir": None,  # default: the configuration's directory
    "memory_limit_mb": 1536,  # whole job: server plus engines
    "below_normal_priority": True,
    "health_interval_s": 10,
    "health_timeout_s": 5,
    "health_failures_before_restart": 3,  # consecutive failures once the server was healthy
    "startup_grace_s": 90,  # an unhealthy start is restarted after this
    "stable_after_s": 600,  # window for counting repeated exits (backoff)
    "max_backoff_s": 60,
    "log_max_mb": 10,
}

CREATE_NO_WINDOW = 0x08000000
CREATE_SUSPENDED = 0x00000004
CREATE_NEW_PROCESS_GROUP = 0x00000200
JOB_OBJECT_LIMIT_PRIORITY_CLASS = 0x00000020
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectBasicProcessIdList = 3
JobObjectExtendedLimitInformation = 9
STILL_ACTIVE = 259
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
ERROR_ALREADY_EXISTS = 183

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True) if os.name == "nt" else None
ntdll = ctypes.WinDLL("ntdll") if os.name == "nt" else None


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class JOBOBJECT_BASIC_PROCESS_ID_LIST(ctypes.Structure):
    _fields_ = [
        ("NumberOfAssignedProcesses", wintypes.DWORD),
        ("NumberOfProcessIdsInList", wintypes.DWORD),
        ("ProcessIdList", ctypes.c_size_t * 64),
    ]


class StartFailure(RuntimeError):
    """The server process could not be started; retried with backoff."""


def process_alive(pid: int | None) -> bool:
    if not pid or kernel32 is None:
        return False
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and (
            code.value == STILL_ACTIVE
        )
    finally:
        kernel32.CloseHandle(handle)


def now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def load_config(path: Path) -> dict:
    config = {**DEFAULTS, **json.loads(path.read_text(encoding="utf-8"))}
    base = path.parent
    if not config["launcher"]:
        raise SystemExit("Configuration needs a launcher.")
    config["launcher"] = str((base / config["launcher"]).resolve())
    config["workdir"] = str(
        (base / (config["workdir"] or Path(config["launcher"]).parent)).resolve()
    )
    config["state_dir"] = str((base / (config["state_dir"] or ".")).resolve())
    return config


class Supervisor:
    def __init__(self, config: dict):
        self.config = config
        self.state = Path(config["state_dir"])
        self.logs = self.state / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.status_path = self.state / "status.json"
        self.child: subprocess.Popen | None = None
        self.job = None
        self.restarts = 0
        self.last_exit: str | None = None
        self.backoff = 0.0
        self.recent_exits: list[float] = []

    # --- logging and status -------------------------------------------------
    def log(self, message: str) -> None:
        path = self.logs / "supervisor.log"
        self._rotate(path)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{now()} {message}\n")

    def _rotate(self, path: Path) -> None:
        limit = self.config["log_max_mb"] * 1024 * 1024
        if path.exists() and path.stat().st_size > limit:
            for index in (2, 1):
                older = path.with_suffix(f"{path.suffix}.{index}")
                if older.exists():
                    older.replace(path.with_suffix(f"{path.suffix}.{index + 1}"))
            path.replace(path.with_suffix(f"{path.suffix}.1"))

    def write_status(self, **extra) -> None:
        status = {
            "supervisor_pid": os.getpid(),
            # The launched process; the listener and engines are its descendants (job_pids).
            "server_pid": self.child.pid if self.child and self.child.poll() is None else None,
            "job_pids": self.job_pids(),
            "restarts": self.restarts,
            "last_exit": self.last_exit,
            "memory_limit_mb": self.config["memory_limit_mb"],
            "health_url": self.config["health_url"],
            "updated": now(),
            **extra,
        }
        temporary = self.status_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(status, indent=2), encoding="utf-8")
        temporary.replace(self.status_path)

    # --- job object ---------------------------------------------------------
    def create_job(self) -> None:
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if self.config["memory_limit_mb"]:
            flags |= JOB_OBJECT_LIMIT_JOB_MEMORY
            info.JobMemoryLimit = int(self.config["memory_limit_mb"]) * 1024 * 1024
        if self.config["below_normal_priority"]:
            flags |= JOB_OBJECT_LIMIT_PRIORITY_CLASS
            info.BasicLimitInformation.PriorityClass = BELOW_NORMAL_PRIORITY_CLASS
        info.BasicLimitInformation.LimitFlags = flags
        if not kernel32.SetInformationJobObject(
            job, JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        self.job = job

    def close_job(self) -> None:
        if self.job:
            kernel32.CloseHandle(self.job)  # kill-on-close ends anything still inside
            self.job = None

    def job_pids(self) -> list[int]:
        info = JOBOBJECT_BASIC_PROCESS_ID_LIST()
        if self.job and kernel32.QueryInformationJobObject(
            self.job, JobObjectBasicProcessIdList, ctypes.byref(info), ctypes.sizeof(info), None
        ):
            return [int(pid) for pid in info.ProcessIdList[: info.NumberOfProcessIdsInList]]
        return []

    def peak_memory_mb(self) -> int | None:
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        if self.job and kernel32.QueryInformationJobObject(
            self.job,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
            None,
        ):
            return round(info.PeakJobMemoryUsed / 1024 / 1024)
        return None

    # --- server lifecycle -----------------------------------------------------
    def start_server(self) -> None:
        # A fresh job for every start: a job that is still being terminated refuses new
        # processes (ERROR_ACCESS_DENIED), and its peak-memory figure belongs to the old run.
        self.close_job()
        self.create_job()
        server_log = self.logs / "server.log"
        self._rotate(server_log)
        output = server_log.open("a", encoding="utf-8")
        output.write(f"\n===== {now()} starting server =====\n")
        output.flush()
        env = {
            **os.environ,
            **{key: str(value) for key, value in self.config["env"].items()},
            "PYTHONUNBUFFERED": "1",
        }
        # CREATE_NO_WINDOW gives the server a hidden console that Stockfish inherits,
        # so no window ever appears, even for the engine processes it starts. It starts
        # suspended so it joins the job before it can start any process of its own.
        self.child = subprocess.Popen(
            [self.config["python"], self.config["launcher"], *self.config["launcher_args"]],
            cwd=self.config["workdir"],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | CREATE_SUSPENDED,
        )
        output.close()
        handle = int(self.child._handle)
        if not kernel32.AssignProcessToJobObject(self.job, handle):
            error = ctypes.get_last_error()
            self.child.kill()
            self.child.wait(15)
            self.child = None
            raise StartFailure(f"could not place the server in its job object (error {error})")
        ntdll.NtResumeProcess(handle)
        self.log(f"server started pid={self.child.pid}")

    def stop_server(self, reason: str) -> None:
        if self.child and self.child.poll() is None:
            self.log(f"stopping server pid={self.child.pid}: {reason}")
        # Terminate every process in the job (server, venv launcher, engines), including
        # any engine left behind by a server that already exited.
        if self.job:
            kernel32.TerminateJobObject(self.job, 1)
        if self.child:
            try:
                self.child.wait(15)
            except subprocess.TimeoutExpired:
                self.child.kill()
        self.child = None
        self.close_job()

    def healthy(self) -> bool:
        try:
            probe = urllib.request.Request(
                self.config["health_url"], headers=self.config["health_headers"]
            )
            with urllib.request.urlopen(probe, timeout=self.config["health_timeout_s"]) as response:
                return response.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def take_request(self) -> str | None:
        for request in ("stop", "restart"):
            path = self.state / f"control.{request}"
            if path.exists():
                path.unlink(missing_ok=True)
                return request
        return None

    def wait(self, seconds: float) -> str | None:
        """Sleep, waking early for control requests or a server exit."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            request = self.take_request()
            if request:
                return request
            if self.child and self.child.poll() is not None:
                return "exited"
            time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
        return None

    def run(self) -> int:
        self.log(f"supervisor started pid={os.getpid()} launcher={self.config['launcher']}")
        for leftover in ("stop", "restart"):
            (self.state / f"control.{leftover}").unlink(missing_ok=True)
        while True:
            started = time.monotonic()
            was_healthy = False
            failures = 0
            outcome = None
            try:
                self.start_server()
                self.write_status(state="starting", started=now())
            except (StartFailure, OSError) as exc:
                self.stop_server("start failed")
                outcome = f"server could not start: {exc}"
            while outcome is None:
                event = self.wait(self.config["health_interval_s"])
                if event == "stop":
                    self.stop_server("stop requested")
                    self.write_status(state="stopped")
                    self.log("supervisor stopped on request")
                    return 0
                if event == "restart":
                    self.stop_server("restart requested")
                    self.backoff = 0
                    outcome = "restart requested"
                    break
                if event == "exited" or (self.child and self.child.poll() is not None):
                    code = self.child.returncode if self.child else None
                    outcome = f"server exited with code {code}"
                    self.stop_server(outcome)
                    break
                if self.healthy():
                    if not was_healthy:
                        self.log("server healthy")
                    was_healthy, failures = True, 0
                    self.write_status(
                        state="healthy",
                        uptime_s=round(time.monotonic() - started),
                        peak_memory_mb=self.peak_memory_mb(),
                    )
                    continue
                failures += 1
                if was_healthy and failures >= self.config["health_failures_before_restart"]:
                    self.stop_server(f"no health response {failures} times in a row")
                    outcome = "server stopped answering"
                elif (
                    not was_healthy and time.monotonic() - started > self.config["startup_grace_s"]
                ):
                    self.stop_server("never became healthy")
                    outcome = "server never became healthy"
                else:
                    self.write_status(
                        state="unhealthy" if was_healthy else "starting", health_failures=failures
                    )
            uptime = time.monotonic() - started
            self.last_exit = f"{now()} {outcome} after {round(uptime)}s"
            self.log(f"{outcome} after {round(uptime)}s")
            if outcome == "restart requested":
                continue
            self.restarts += 1
            # A server that was serving comes straight back. Back off only when it keeps
            # failing: three exits within stable_after_s, or it never became healthy.
            moment = time.monotonic()
            self.recent_exits = [
                t for t in self.recent_exits if moment - t < self.config["stable_after_s"]
            ] + [moment]
            if was_healthy and len(self.recent_exits) < 3:
                self.backoff = 1
            else:
                self.backoff = min(self.config["max_backoff_s"], max(2, self.backoff * 2))
            self.write_status(state="restarting", next_start_in_s=self.backoff)
            if self.wait(self.backoff) == "stop":
                self.write_status(state="stopped")
                self.log("supervisor stopped on request")
                return 0


def single_instance(name: str):
    """A per-session named mutex; returns None when another supervisor holds it."""
    digest = hashlib.sha256(name.encode()).hexdigest()[:16]
    handle = kernel32.CreateMutexW(None, False, f"Local\\AIChessLoungeSupervisor-{digest}")
    if not handle or ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return None
    return handle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument(
        "command", nargs="?", default="run", choices=["run", "status", "restart", "stop"]
    )
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config.resolve())
    except (OSError, ValueError, SystemExit) as exc:
        # pythonw has no console: leave the reason next to the configuration.
        crash = args.config.resolve().parent / "supervisor-config-error.log"
        crash.write_text(f"{now()} could not load {args.config}: {exc!r}\n", encoding="utf-8")
        raise
    state = Path(config["state_dir"])
    if args.command == "status":
        path = state / "status.json"
        status = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if (
            status
            and status.get("state") != "stopped"
            and not process_alive(status.get("supervisor_pid"))
        ):
            # A status written by a supervisor that no longer exists is not the truth.
            status = {**status, "state": "not running", "last_state": status.get("state")}
        print(json.dumps(status, indent=2))
        return 0
    if args.command in ("restart", "stop"):
        state.mkdir(parents=True, exist_ok=True)
        (state / f"control.{args.command}").write_text(now(), encoding="utf-8")
        print(f"{args.command} requested")
        return 0
    if os.name != "nt":
        raise SystemExit(
            "The Lounge supervisor uses Windows job objects; use systemd or Docker elsewhere."
        )
    mutex = single_instance(str(args.config.resolve()).lower())
    supervisor = Supervisor(config)
    if mutex is None:
        supervisor.log("another supervisor is already running for this configuration; exiting")
        return 0
    try:
        return supervisor.run()
    except Exception as exc:  # Never die silently: the scheduled task restarts us.
        supervisor.log(f"supervisor crashed: {exc!r} {traceback.format_exc()}")
        supervisor.stop_server("supervisor crashed")
        supervisor.write_status(state="crashed", error=repr(exc))
        raise
    finally:
        supervisor.stop_server("supervisor exiting")


if __name__ == "__main__":
    sys.exit(main())
