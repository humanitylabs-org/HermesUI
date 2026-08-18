#!/usr/bin/env python3
"""Safely acquire the shared HermesUI lifecycle lock and exec a command."""

from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import stat
import sys
from typing import NoReturn

BUSY_EXIT = 75


def fail(message: str, code: int = 1) -> NoReturn:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def lexical_absolute(raw: str) -> Path:
    if not raw:
        fail("HermesUI lifecycle lock path is empty")
    path = Path(os.path.abspath(os.path.expanduser(raw)))
    if path.name in {"", ".", ".."}:
        fail("HermesUI lifecycle lock path has no filename")
    return path


def reject_symlink_ancestors(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:-1]:
        current /= part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            return
        if stat.S_ISLNK(info.st_mode):
            fail(f"HermesUI lifecycle lock ancestor is a symlink: {current}")
        if not stat.S_ISDIR(info.st_mode):
            fail(f"HermesUI lifecycle lock ancestor is not a directory: {current}")


def open_private_parent(path: Path) -> int:
    reject_symlink_ancestors(path)
    parent = path.parent
    if not parent.exists():
        try:
            os.mkdir(parent, 0o700)
        except FileExistsError:
            pass
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(parent, flags)
    except OSError as exc:
        fail(f"could not open private lifecycle-lock directory {parent}: {exc}")
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode):
        os.close(fd)
        fail(f"lifecycle-lock parent is not a directory: {parent}")
    if info.st_uid != os.getuid():
        os.close(fd)
        fail(f"lifecycle-lock directory is not owned by uid {os.getuid()}: {parent}")
    if stat.S_IMODE(info.st_mode) & 0o077:
        os.close(fd)
        fail(f"lifecycle-lock directory must be private (mode 0700): {parent}")
    return fd


def validate_lock_fd(fd: int, path: Path) -> None:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        fail("HermesUI lifecycle lock is not a regular file")
    if info.st_uid != os.getuid():
        fail("HermesUI lifecycle lock is not owned by the invoking uid")
    if info.st_nlink != 1:
        fail("HermesUI lifecycle lock must have exactly one hard link")
    if stat.S_IMODE(info.st_mode) != 0o600:
        fail("HermesUI lifecycle lock must have mode 0600")
    try:
        path_info = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        fail(f"could not verify HermesUI lifecycle lock path: {exc}")
    if stat.S_ISLNK(path_info.st_mode):
        fail("HermesUI lifecycle lock path is a symlink")
    if (path_info.st_dev, path_info.st_ino) != (info.st_dev, info.st_ino):
        fail("HermesUI lifecycle lock descriptor no longer matches its path")


def acquire(path: Path) -> int:
    parent_fd = open_private_parent(path)
    flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path.name, flags, 0o600, dir_fd=parent_fd)
    except OSError as exc:
        os.close(parent_fd)
        fail(f"could not safely open HermesUI lifecycle lock: {exc}")
    finally:
        try:
            os.close(parent_fd)
        except OSError:
            pass
    validate_lock_fd(fd, path)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        fail("another HermesUI setup, update, or uninstall is already running.", BUSY_EXIT)
    return fd


def verify_inherited(path: Path, fd: int) -> int:
    open_private_parent_fd = open_private_parent(path)
    os.close(open_private_parent_fd)
    try:
        validate_lock_fd(fd, path)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fail("inherited HermesUI lifecycle lock is not exclusively held", BUSY_EXIT)
    except OSError as exc:
        fail(f"inherited HermesUI lifecycle lock is invalid: {exc}", BUSY_EXIT)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", required=True)
    parser.add_argument("--fd", type=int, default=9)
    parser.add_argument("--verify-inherited", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    path = lexical_absolute(args.lock)
    if args.verify_inherited:
        return verify_inherited(path, args.fd)
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        fail("no lifecycle command was provided")
    fd = acquire(path)
    if fd != args.fd:
        os.dup2(fd, args.fd, inheritable=True)
        os.close(fd)
    os.set_inheritable(args.fd, True)
    env = os.environ.copy()
    env["HERMESUI_LIFECYCLE_LOCK_HELD"] = "1"
    env["HERMESUI_LIFECYCLE_LOCK_FILE"] = str(path)
    os.execvpe(command[0], command, env)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
