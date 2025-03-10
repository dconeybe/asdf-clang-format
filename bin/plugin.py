#!/usr/bin/env python3

import argparse
import dataclasses
import logging
import os
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
  versions = get_llvm_versions()
  print(" ".join(versions))


def install(version_to_install: str) -> None:
  logging.info("Installing clang-format version %s", version_to_install)
  versions = get_llvm_versions()
  print(" ".join(versions))


def get_llvm_versions() -> list[str]:
  url = "https://api.github.com/repos/llvm/llvm-project/releases"
  headers = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  }
  logging.info("Getting releases from %s", url)

  response = requests.get(url, headers=headers)
  response.raise_for_status()
  releases = response.json()

  release_names = tuple(release["name"] for release in releases)

  return [release_name[5:] for release_name in release_names]


if __name__ == "__main__":
  main()
