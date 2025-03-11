#!/usr/bin/env python3

import argparse
from collections.abc import Sequence
import dataclasses
import logging
import sys

import requests


def main() -> None:
  arg_parser = argparse.ArgumentParser()
  arg_parser.add_argument("--log-level", default=None, choices=("info", "debug", "warning"))
  arg_parser.set_defaults(command=None)
  subparsers = arg_parser.add_subparsers()

  list_all_subparser = subparsers.add_parser("list-all")
  list_all_subparser.set_defaults(command="list-all")

  install_subparser = subparsers.add_parser("install")
  install_subparser.set_defaults(command="install")
  install_subparser.add_argument("--install-version", required=True)

  parsed_args = arg_parser.parse_args()

  match parsed_args.log_level:
    case None:
      logging.basicConfig()
    case "info":
      logging.basicConfig(level=logging.INFO)
    case "debug":
      logging.basicConfig(level=logging.DEBUG)
    case "warning":
      logging.basicConfig(level=logging.WARNING)
    case unknown_log_level:
      raise Exception(f"internal error a37myxrv6a: unknown log level name: {unknown_log_level}")

  match parsed_args.command:
    case None:
      print("ERROR: no sub-command specified", file=sys.stderr)
      print("Run with --help for help", file=sys.stderr)
      sys.exit(2)
    case "list-all":
      list_all()
    case "install":
      install(parsed_args.install_version)
    case unknown_command:
      raise Exception(f"internal error ysnynaqa84: unknown command: {unknown_command}")


def list_all() -> None:
  releases = get_llvm_releases()
  versions_str = " ".join(release.version for release in releases)
  print(versions_str)


def install(version_to_install: str) -> None:
  logging.info("Installing clang-format version %s", version_to_install)
  releases = get_llvm_releases()
  releases_to_install = [release for release in releases if release.version == version_to_install]

  if len(releases_to_install) == 0:
    print(f"ERROR: version not found: {version_to_install}", file=sys.stderr)
    sys.exit(1)
  elif len(releases_to_install) > 1:
    print(
        f"ERROR: {len(releases_to_install)} versions found "
        f"for version {version_to_install}, but expected exactly 1.",
        file=sys.stderr,
    )
    sys.exit(1)

  release_to_install = releases_to_install[0]
  import pprint

  pprint.pprint(releases_to_install)


@dataclasses.dataclass(frozen=True)
class LlvmReleaseAsset:
  name: str
  size: int
  download_url: str


@dataclasses.dataclass(frozen=True)
class LlvmReleaseInfo:
  version: str
  assets: Sequence[LlvmReleaseAsset]


def get_llvm_releases() -> list[LlvmReleaseInfo]:
  url = "https://api.github.com/repos/llvm/llvm-project/releases"
  headers = {
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
  }
  logging.info("Getting releases from %s", url)

  response = requests.get(url, headers=headers)
  response.raise_for_status()
  releases = response.json()

  llvm_release_infos: list[LlvmReleaseInfo] = []
  for release in releases:
    release_name = release["name"]
    version = release_name[5:]

    llvm_release_assets: list[LlvmReleaseAsset] = []
    assets = release.get("assets", [])
    if assets:
      for asset in assets:
        llvm_release_assets.append(
            LlvmReleaseAsset(
                name=asset["name"],
                size=asset["size"],
                download_url=asset["browser_download_url"],
            )
        )

    llvm_release_infos.append(LlvmReleaseInfo(version=version, assets=llvm_release_assets))

  return llvm_release_infos


if __name__ == "__main__":
  main()
