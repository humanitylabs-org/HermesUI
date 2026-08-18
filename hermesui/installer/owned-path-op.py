#!/usr/bin/env python3
"""Atomic compare-and-swap operations for installer-owned files.

The destination and quarantine paths must share a filesystem. A path is first
moved atomically to a private quarantine name, then verified there. If another
same-user process replaced the destination at the boundary, its bytes are
restored without clobbering anything that appeared afterward.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import os
import secrets
import stat
import sys
from pathlib import Path

AT_FDCWD = -100
RENAME_NOREPLACE = 1


def digest(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    h = hashlib.sha256()
    with os.fdopen(fd, "rb") as handle:
        st = os.fstat(handle.fileno())
        if not stat.S_ISREG(st.st_mode):
            raise RuntimeError(f"refusing non-regular path: {path}")
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rename_noreplace(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is not None:
        result = renameat2(
            AT_FDCWD,
            os.fsencode(source),
            AT_FDCWD,
            os.fsencode(destination),
            RENAME_NOREPLACE,
        )
        if result == 0:
            return
        error = ctypes.get_errno()
        if error not in {errno.ENOSYS, errno.EINVAL}:
            raise OSError(error, os.strerror(error), str(destination))
    # Same-filesystem regular-file fallback. link() is atomic and fails if the
    # destination appeared, then unlinking the source completes the move.
    os.link(source, destination, follow_symlinks=False)
    os.unlink(source)


def quarantine_name(path: Path) -> Path:
    return path.with_name(f".{path.name}.hermesui-quarantine-{os.getpid()}-{secrets.token_hex(8)}")


def restore_quarantine(quarantine: Path, destination: Path) -> None:
    try:
        rename_noreplace(quarantine, destination)
    except FileExistsError as exc:
        raise RuntimeError(
            f"destination changed again; preserved displaced bytes at {quarantine}"
        ) from exc


def move_verified(destination: Path, expected: str) -> Path:
    quarantine = quarantine_name(destination)
    try:
        os.rename(destination, quarantine)
    except FileNotFoundError as exc:
        raise RuntimeError(f"owned path disappeared: {destination}") from exc
    try:
        actual = digest(quarantine)
    except Exception:
        restore_quarantine(quarantine, destination)
        raise
    if actual != expected:
        restore_quarantine(quarantine, destination)
        raise RuntimeError(
            f"ownership changed at mutation boundary for {destination}; current bytes were preserved"
        )
    return quarantine


def publish(source: Path, destination: Path, expected: str | None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if expected is None:
        rename_noreplace(source, destination)
        return
    source_digest = digest(source)
    quarantine = move_verified(destination, expected)
    try:
        rename_noreplace(source, destination)
    except Exception:
        try:
            restore_quarantine(quarantine, destination)
        except Exception as restore_error:
            raise RuntimeError(
                f"publish failed and prior owned bytes remain at {quarantine}: {restore_error}"
            ) from restore_error
        raise
    try:
        quarantine.unlink()
    except Exception as cleanup_error:
        candidate_quarantine = move_verified(destination, source_digest)
        try:
            restore_quarantine(quarantine, destination)
            restore_quarantine(candidate_quarantine, source)
        except Exception as restore_error:
            raise RuntimeError(
                "post-publication cleanup failed and compensation was incomplete; "
                f"preserved bytes at {quarantine} and {candidate_quarantine}: {restore_error}"
            ) from restore_error
        raise RuntimeError(
            f"post-publication cleanup failed; original state was restored: {cleanup_error}"
        ) from cleanup_error


def remove(destination: Path, expected: str) -> None:
    quarantine = move_verified(destination, expected)
    try:
        quarantine.unlink()
    except Exception as cleanup_error:
        try:
            restore_quarantine(quarantine, destination)
        except Exception as restore_error:
            raise RuntimeError(
                f"remove cleanup failed and prior bytes remain at {quarantine}: {restore_error}"
            ) from restore_error
        raise RuntimeError(
            f"remove cleanup failed; original state was restored: {cleanup_error}"
        ) from cleanup_error


def read_symlink(path: Path) -> str:
    try:
        return os.readlink(path)
    except OSError as exc:
        raise RuntimeError(f"refusing non-symlink path: {path}") from exc


def require_target_digest(target: str, expected: str | None) -> None:
    if expected is None:
        return
    try:
        actual = digest(Path(target))
    except Exception as exc:
        raise RuntimeError(f"enable-link target could not be verified: {target}") from exc
    if actual != expected:
        raise RuntimeError(f"enable-link target changed ownership: {target}")


def create_symlink(target: str, destination: Path, expected_target_digest: str | None = None) -> None:
    require_target_digest(target, expected_target_digest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    candidate = destination.with_name(
        f".{destination.name}.hermesui-link-{os.getpid()}-{secrets.token_hex(8)}"
    )
    os.symlink(target, candidate)
    candidate_stat = candidate.lstat()
    try:
        rename_noreplace(candidate, destination)
    except Exception:
        candidate.unlink(missing_ok=True)
        raise
    try:
        require_target_digest(target, expected_target_digest)
    except Exception:
        try:
            published_stat = destination.lstat()
            if (published_stat.st_dev, published_stat.st_ino) != (
                candidate_stat.st_dev,
                candidate_stat.st_ino,
            ):
                raise RuntimeError(
                    "enable-link target changed and the published link was replaced; "
                    "the replacement was preserved"
                )
            destination.unlink()
        except FileNotFoundError:
            pass
        raise


def remove_symlink(
    destination: Path,
    expected_target: str,
    expected_target_digest: str | None = None,
) -> None:
    require_target_digest(expected_target, expected_target_digest)
    quarantine = quarantine_name(destination)
    try:
        os.rename(destination, quarantine)
    except FileNotFoundError as exc:
        raise RuntimeError(f"owned symlink disappeared: {destination}") from exc
    try:
        actual_target = read_symlink(quarantine)
    except Exception:
        restore_quarantine(quarantine, destination)
        raise
    if actual_target != expected_target:
        restore_quarantine(quarantine, destination)
        raise RuntimeError(
            f"symlink ownership changed at mutation boundary for {destination}; current target was preserved"
        )
    try:
        require_target_digest(expected_target, expected_target_digest)
    except Exception:
        restore_quarantine(quarantine, destination)
        raise
    try:
        quarantine.unlink()
    except Exception as cleanup_error:
        try:
            restore_quarantine(quarantine, destination)
        except Exception as restore_error:
            raise RuntimeError(
                f"symlink cleanup failed and prior link remains at {quarantine}: {restore_error}"
            ) from restore_error
        raise RuntimeError(
            f"symlink cleanup failed; original link was restored: {cleanup_error}"
        ) from cleanup_error


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    digest_parser = sub.add_parser("digest")
    digest_parser.add_argument("path", type=Path)

    publish_parser = sub.add_parser("publish")
    publish_parser.add_argument("source", type=Path)
    publish_parser.add_argument("destination", type=Path)
    publish_parser.add_argument("--expected")

    remove_parser = sub.add_parser("remove")
    remove_parser.add_argument("destination", type=Path)
    remove_parser.add_argument("--expected", required=True)

    readlink_parser = sub.add_parser("readlink")
    readlink_parser.add_argument("path", type=Path)

    symlink_create_parser = sub.add_parser("symlink-create")
    symlink_create_parser.add_argument("target")
    symlink_create_parser.add_argument("destination", type=Path)
    symlink_create_parser.add_argument("--expected-target-digest")

    symlink_remove_parser = sub.add_parser("symlink-remove")
    symlink_remove_parser.add_argument("destination", type=Path)
    symlink_remove_parser.add_argument("--expected-target", required=True)
    symlink_remove_parser.add_argument("--expected-target-digest")

    args = parser.parse_args()
    try:
        if args.command == "digest":
            print(digest(args.path))
        elif args.command == "publish":
            publish(args.source, args.destination, args.expected)
        elif args.command == "remove":
            remove(args.destination, args.expected)
        elif args.command == "readlink":
            print(read_symlink(args.path))
        elif args.command == "symlink-create":
            create_symlink(args.target, args.destination, args.expected_target_digest)
        elif args.command == "symlink-remove":
            remove_symlink(
                args.destination,
                args.expected_target,
                args.expected_target_digest,
            )
        return 0
    except FileExistsError:
        print(f"ERROR: destination appeared before atomic publication: {getattr(args, 'destination', '')}", file=sys.stderr)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
