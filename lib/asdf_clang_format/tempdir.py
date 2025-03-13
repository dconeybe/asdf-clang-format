from __future__ import annotations

import abc
import contextlib
import pathlib
import tempfile
from types import TracebackType
from typing import final
import typing


class TempDir(contextlib.AbstractContextManager[pathlib.Path]):
  @property
  @abc.abstractmethod
  def path(self) -> pathlib.Path: ...

  @abc.abstractmethod
  def cleanup(self) -> None: ...

  def subdir(self, name: str) -> pathlib.Path:
    scrubbed_name = scrubbed_file_name(name)
    temp_sub_dir = tempfile.mkdtemp(prefix=f"{scrubbed_name}_", dir=self.path)
    return pathlib.Path(temp_sub_dir)


class TempDirFactory(typing.Protocol):
  def get(self, name: str) -> TempDir: ...


@final
class PersistentTempDir(TempDir):
  def __init__(self, path: pathlib.Path) -> None:
    self._path = path

  @property
  @typing.override
  def path(self) -> pathlib.Path:
    return self._path

  @typing.override
  def cleanup(self) -> None:
    # Do nothing on cleanup; we are a "persistent" temporary directory after all.
    pass

  def __str__(self) -> str:
    return self.path.__str__()

  def __repr__(self) -> str:
    return f"PersistentTempDir({self.path!r})"

  @typing.override
  def __enter__(self) -> pathlib.Path:
    return self.path

  @typing.override
  def __exit__(
    self,
    exc_type: type[BaseException] | None,
    exc_value: BaseException | None,
    traceback: TracebackType | None,
  ) -> bool | None:
    pass


@final
class PersistentTempDirFactory(TempDirFactory):
  def __init__(self, path: pathlib.Path) -> None:
    self.path = path

  def get(self, name: str) -> PersistentTempDir:
    scrubbed_name = scrubbed_file_name(name)
    self.path.mkdir(parents=True, exist_ok=True)
    temp_dir = tempfile.mkdtemp(prefix=f"{scrubbed_name}_", dir=self.path)
    return PersistentTempDir(pathlib.Path(temp_dir))


@final
class EphemeralTempDir(TempDir):
  def __init__(self, temp_dir: tempfile.TemporaryDirectory[str]) -> None:
    self.temp_dir = temp_dir
    self._path = pathlib.Path(temp_dir.name)

  @property
  @typing.override
  def path(self) -> pathlib.Path:
    return self._path

  @typing.override
  def cleanup(self) -> None:
    self.temp_dir.cleanup()

  def __str__(self) -> str:
    return self.temp_dir.__str__()

  def __repr__(self) -> str:
    return f"EphemeralTempDir({self.temp_dir!r})"

  @typing.override
  def __enter__(self) -> pathlib.Path:
    self.temp_dir.__enter__()
    return self.path

  @typing.override
  def __exit__(
    self,
    exc_type: type[BaseException] | None,
    exc_value: BaseException | None,
    traceback: TracebackType | None,
  ) -> bool | None:
    return self.temp_dir.__exit__(exc_type, exc_value, traceback)


@final
class EphemeralTempDirFactory(TempDirFactory):
  def get(self, name: str) -> EphemeralTempDir:
    scrubbed_name = scrubbed_file_name(name)
    temp_dir = tempfile.TemporaryDirectory(prefix=f"{scrubbed_name}_")
    return EphemeralTempDir(temp_dir)


def scrubbed_file_name(file_name: str) -> str:
  return "".join(c if c.isalnum() or c.isidentifier() else "_" for c in file_name)
