"""What ARDA asks the operating system about processes, files and the user, on Linux and Windows.

Linux answers from /proc and the user database. Windows answers from the process
snapshot, process handles and the user's token, through ctypes. Neither takes an
answer from the environment, which is the caller's to set.
"""

import contextlib
import os
import signal
import sys

WINDOWS = sys.platform == 'win32'

if not WINDOWS:
    import pwd

    def real_home():
        """The user's home directory from the user database: $HOME is the caller's to set."""
        return os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)

    def parent(pid):
        try:
            with open(f'/proc/{pid}/stat') as handle:
                return int(handle.read().rsplit(')', 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            return 0

    def name(pid):
        try:
            with open(f'/proc/{pid}/comm') as handle:
                return handle.read().strip()
        except OSError:
            return None

    def executable(pid):
        try:
            return os.readlink(f'/proc/{pid}/exe').removesuffix(' (deleted)')  # updated since: same path
        except OSError:
            return None

    def opened_path(fd):
        return os.readlink(f'/proc/self/fd/{fd}')

    POPEN = {'start_new_session': True}

    def kill_tree(proc):
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)

else:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _advapi = ctypes.WinDLL('advapi32', use_last_error=True)
    _userenv = ctypes.WinDLL('userenv', use_last_error=True)
    _INVALID = ctypes.c_void_p(-1).value
    _QUERY = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
    _TERMINATE = 0x0001

    class _Entry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                    ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', wintypes.DWORD),
                    ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                    ('pcPriClassBase', wintypes.LONG), ('dwFlags', wintypes.DWORD),
                    ('szExeFile', wintypes.WCHAR * 260)]

    for _fn, _args, _res in (
            (_k32.CreateToolhelp32Snapshot, (wintypes.DWORD, wintypes.DWORD), wintypes.HANDLE),
            (_k32.Process32FirstW, (wintypes.HANDLE, ctypes.POINTER(_Entry)), wintypes.BOOL),
            (_k32.Process32NextW, (wintypes.HANDLE, ctypes.POINTER(_Entry)), wintypes.BOOL),
            (_k32.OpenProcess, (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD), wintypes.HANDLE),
            (_k32.CloseHandle, (wintypes.HANDLE,), wintypes.BOOL),
            (_k32.GetCurrentProcess, (), wintypes.HANDLE),
            (_k32.GetProcessTimes, (wintypes.HANDLE, *[ctypes.POINTER(ctypes.c_uint64)] * 4), wintypes.BOOL),
            (_k32.TerminateProcess, (wintypes.HANDLE, wintypes.UINT), wintypes.BOOL),
            (_k32.QueryFullProcessImageNameW,
             (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)), wintypes.BOOL),
            (_k32.GetFinalPathNameByHandleW,
             (wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD), wintypes.DWORD),
            (_advapi.OpenProcessToken, (wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)),
             wintypes.BOOL),
            (_userenv.GetUserProfileDirectoryW,
             (wintypes.HANDLE, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)), wintypes.BOOL)):
        _fn.argtypes, _fn.restype = _args, _res

    def _snapshot():
        """{pid: (parent pid, image name)} for every process now."""
        snap = _k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
        if snap in (None, _INVALID):
            return {}
        try:
            entry, found = _Entry(), {}
            entry.dwSize = ctypes.sizeof(_Entry)
            ok = _k32.Process32FirstW(snap, ctypes.byref(entry))
            while ok:
                found[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile)
                ok = _k32.Process32NextW(snap, ctypes.byref(entry))
            return found
        finally:
            _k32.CloseHandle(snap)

    @contextlib.contextmanager
    def _process(pid, access=_QUERY):
        handle = _k32.OpenProcess(access, False, pid)
        try:
            yield handle or None
        finally:
            if handle:
                _k32.CloseHandle(handle)

    def _created(pid):
        with _process(pid) as handle:
            times = [ctypes.c_uint64() for _ in range(4)]
            if handle and _k32.GetProcessTimes(handle, *map(ctypes.byref, times)):
                return times[0].value
        return None

    def _descends(child, ancestor):
        """Windows keeps a dead parent's pid in its children, and pids are reused: a parent only counts
        if it was created before the child."""
        born, before = _created(child), _created(ancestor)
        return born is not None and before is not None and before <= born

    def real_home():
        """The user's profile directory from the user's token: %USERPROFILE% is the caller's to set."""
        token = wintypes.HANDLE()
        if not _advapi.OpenProcessToken(_k32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):  # TOKEN_QUERY
            raise OSError(ctypes.get_last_error(), 'cannot open the process token')
        try:
            size = wintypes.DWORD(32768)
            buf = ctypes.create_unicode_buffer(size.value)
            if not _userenv.GetUserProfileDirectoryW(token, buf, ctypes.byref(size)):
                raise OSError(ctypes.get_last_error(), 'cannot read the user profile directory')
            return os.path.realpath(buf.value)
        finally:
            _k32.CloseHandle(token)

    def parent(pid):
        ppid = _snapshot().get(pid, (0,))[0]
        return ppid if ppid and _descends(pid, ppid) else 0

    def name(pid):
        """The image name without .exe, as /proc/PID/comm would give it."""
        entry = _snapshot().get(pid)
        return entry[1].removesuffix('.exe').removesuffix('.EXE') if entry else None

    def executable(pid):
        with _process(pid) as handle:
            size = wintypes.DWORD(32768)
            buf = ctypes.create_unicode_buffer(size.value)
            if handle and _k32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return buf.value
        return None

    def _plain(path):
        if path.startswith('\\\\?\\UNC\\'):
            return '\\\\' + path[8:]
        return path.removeprefix('\\\\?\\')

    def opened_path(fd):
        buf = ctypes.create_unicode_buffer(32768)
        if not _k32.GetFinalPathNameByHandleW(msvcrt.get_osfhandle(fd), buf, 32768, 0):
            raise OSError(ctypes.get_last_error(), 'cannot tell which file was opened')
        return _plain(buf.value)

    POPEN = {}

    def kill_tree(proc):
        """Stop a process and every process it started (Windows has no process groups to signal)."""
        processes = _snapshot()
        doomed, queue = [], [proc.pid]
        while queue:
            pid = queue.pop()
            doomed.append(pid)
            queue += [child for child, (ppid, _) in processes.items()
                      if ppid == pid and child not in doomed and _descends(child, pid)]
        for pid in doomed:
            with _process(pid, _TERMINATE) as handle:
                if handle:
                    _k32.TerminateProcess(handle, 1)
