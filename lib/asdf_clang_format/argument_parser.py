from __future__ import annotations

import argparse
from collections.abc import Callable, Iterable
import dataclasses
import enum
import logging
import os
import pathlib
from typing import final, NoReturn
import typing

from .tempdir import EphemeralTempDirFactory, PersistentTempDirFactory, TempDirFactory


@final
class ArgumentParser:
  def __init__(self) -> None:
    self.arg_parser = argparse.ArgumentParser()
    self.sub_command_names: list[str] = []
    self._add_global_args(self.arg_parser)
    self._add_commands()

  def parse(self) -> ParsedArguments:
    namespace = _Namespace()
    self.arg_parser.parse_args(namespace=namespace)
    return namespace.to_parsed_arguments(
      sub_command_names=self.sub_command_names,
      on_error=self.arg_parser.error,
    )

  @staticmethod
  def _add_global_args(arg_parser: argparse.ArgumentParser) -> None:
    arg_parser.set_defaults(
      command_name=None,
      log_level_name=None,
    )

    arg_parser.add_argument(
      "--temp-dir",
      default=None,
      help="The directory to use as a temporary directory, instead of creating and deleting "
      "ephemeral temporary directories. (useful for debugging)",
    )

    log_level_arg = arg_parser.add_argument(
      "--log-level",
      dest="log_level_name",
      default="info",
      choices=("debug", "info", "warn"),
      help="The level of log output to emit (default: %(default)s)",
    )

    arg_parser.add_argument(
      "-v",
      "--verbose",
      action="store_const",
      const="debug",
      dest=log_level_arg.dest,
      help=f"shorthand for {log_level_arg.option_strings[0]}=%(const)s",
    )

    arg_parser.add_argument(
      "-q",
      "--quiet",
      action="store_const",
      const="warn",
      dest=log_level_arg.dest,
      help=f"shorthand for {log_level_arg.option_strings[0]}=%(const)s",
    )

  def _add_commands(self) -> None:
    subparsers = self.arg_parser.add_subparsers()
    self._add_list_all_command(subparsers)
    self._add_download_command(subparsers)
    self._add_install_command(subparsers)

  def _add_sub_command(self, subparsers: _Subparsers, command_name: str) -> argparse.ArgumentParser:
    self.sub_command_names.append(command_name)
    subparser = subparsers.add_parser(command_name)
    subparser.set_defaults(command_name=command_name)
    return subparser

  def _add_list_all_command(self, subparsers: _Subparsers) -> None:
    self._add_sub_command(subparsers, "list-all")

  def _add_download_command(self, subparsers: _Subparsers) -> None:
    subparser = self._add_sub_command(subparsers, "download")
    subparser.set_defaults(stop_after_name=None)
    self._add_clang_format_version_argument(subparser)
    self._add_download_dir_argument(subparser)
    subparser.add_argument(
      "--stop-after-download",
      dest="stop_after_name",
      action="store_const",
      const="download",
      default=None,
    )
    subparser.add_argument(
      "--stop-after-verify",
      dest="stop_after_name",
      action="store_const",
      const="verify",
      default=None,
    )

  def _add_install_command(self, subparsers: _Subparsers) -> None:
    subparser = self._add_sub_command(subparsers, "install")
    self._add_clang_format_version_argument(subparser)
    self._add_download_dir_argument(subparser)
    subparser.add_argument("--install-dir", required=True)

  @staticmethod
  def _add_download_dir_argument(arg_parser: argparse.ArgumentParser) -> None:
    arg_parser.add_argument("--download-dir", required=True)

  @staticmethod
  def _add_clang_format_version_argument(arg_parser: argparse.ArgumentParser) -> None:
    arg_parser.add_argument("--clang-format-version", required=True)


class _Subparsers(typing.Protocol):
  """The return type of ArgumentParser.add_subparsers()."""

  def add_parser(self, name: str) -> argparse.ArgumentParser: ...


@dataclasses.dataclass(frozen=True)
class ListAllCommand:
  pass


@dataclasses.dataclass(frozen=True)
class DownloadCommand:
  clang_format_version: str
  download_dir: pathlib.Path
  stop_after: DownloadCommand.StopAfter | None

  class StopAfter(enum.StrEnum):
    DOWNLOAD = enum.auto()
    VERIFY = enum.auto()


@dataclasses.dataclass(frozen=True)
class InstallCommand:
  clang_format_version: str
  download_dir: pathlib.Path
  install_dir: pathlib.Path


type ParsedCommand = ListAllCommand | DownloadCommand | InstallCommand


@dataclasses.dataclass(frozen=True)
class ParsedArguments:
  log_level: int
  temp_dir_factory: TempDirFactory
  command: ParsedCommand


class _Namespace(argparse.Namespace):
  def __init__(self) -> None:
    super().__init__()

  def to_parsed_arguments(
    self,
    sub_command_names: Iterable[str],
    on_error: Callable[[str], NoReturn],
  ) -> ParsedArguments:
    command = self.parsed_command_from_command_name()
    if command is None:
      sub_command_names_str = ", ".join(sorted(sub_command_names))
      on_error(
        f"no sub-command specified, but one is required;{os.linesep}"
        f"valid sub-command are: {sub_command_names_str}{os.linesep}"
        "Run with --help for help"
      )
      typing.assert_never("internal error b2kwnwk7q7: on_error() should have raised an exception")

    return ParsedArguments(
      log_level=self.log_level_from_log_level_name(default_log_level=logging.INFO),
      temp_dir_factory=self.temp_dir_factory_from_temp_dir(),
      command=command,
    )

  def log_level_from_log_level_name(self, default_log_level: int) -> int:
    match self.log_level_name:
      case None:
        return default_log_level
      case "debug":
        return logging.DEBUG
      case "info":
        return logging.INFO
      case "warn":
        return logging.WARN
      case unknown_log_level_name:
        raise self.UnknownLogLevelName(
          f"unknown log level name: {unknown_log_level_name} (error code zrdafchjkq)"
        )

  def parsed_command_from_command_name(self) -> ParsedCommand | None:
    match self.command_name:
      case None:
        return None
      case "list-all":
        return self.to_list_all_command()
      case "download":
        return self.to_download_command()
      case "install":
        return self.to_install_command()
      case unknown_command_name:
        raise self.UnknownLogLevelName(
          f"unknown command name: {unknown_command_name} (error code tvgpnz56pr)"
        )

  def path_from_download_dir(self) -> pathlib.Path:
    return pathlib.Path(self.download_dir)

  def path_from_install_dir(self) -> pathlib.Path:
    return pathlib.Path(self.install_dir)

  def download_stop_after_from_stop_after_name(self) -> DownloadCommand.StopAfter | None:
    match self.stop_after_name:
      case None:
        return None
      case "download":
        return DownloadCommand.StopAfter.DOWNLOAD
      case "verify":
        return DownloadCommand.StopAfter.VERIFY
      case unknown_stop_after_name:
        raise self.UnknownDownloadStopAfterName(
          f"unknown stop-after name: {unknown_stop_after_name} (error code pjvqdrrqbs)"
        )

  def temp_dir_factory_from_temp_dir(self) -> TempDirFactory:
    match self.temp_dir:
      case None:
        return EphemeralTempDirFactory()
      case temp_dir:
        return PersistentTempDirFactory(pathlib.Path(temp_dir))

  def to_list_all_command(self) -> ListAllCommand:
    return ListAllCommand()

  def to_download_command(self) -> DownloadCommand:
    return DownloadCommand(
      clang_format_version=self.clang_format_version,
      download_dir=self.path_from_download_dir(),
      stop_after=self.download_stop_after_from_stop_after_name(),
    )

  def to_install_command(self) -> InstallCommand:
    return InstallCommand(
      clang_format_version=self.clang_format_version,
      download_dir=self.path_from_download_dir(),
      install_dir=self.path_from_install_dir(),
    )

  class UnknownCommandName(Exception):
    pass

  class UnknownLogLevelName(Exception):
    pass

  class UnknownDownloadStopAfterName(Exception):
    pass
