#!/usr/bin/env python3

import argparse
from collections.abc import Sequence
import dataclasses
import logging
import pathlib
import platform
import sys
import tarfile
import tempfile

import gnupg
import requests
import tqdm


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
  install_subparser.add_argument("--download-dir", required=True)
  install_subparser.add_argument("--install-dir", required=True)
  install_subparser.add_argument("--llvm-release-keys-file", required=True)

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
      print("ERROR: no sub-command specified (error code j53fg4ce6r)", file=sys.stderr)
      print("Run with --help for help", file=sys.stderr)
      sys.exit(2)
    case "list-all":
      list_all()
    case "install":
      version_to_install = parsed_args.install_version
      download_dir = pathlib.Path(parsed_args.download_dir)
      install_dir = pathlib.Path(parsed_args.install_dir)
      llvm_release_keys_file = pathlib.Path(parsed_args.llvm_release_keys_file)
      install(
          version_to_install=version_to_install,
          download_dir=download_dir,
          install_dir=install_dir,
          llvm_release_keys_file=llvm_release_keys_file,
      )
    case unknown_command:
      raise Exception(f"internal error ysnynaqa84: unknown command: {unknown_command}")


def list_all() -> None:
  releases = get_llvm_releases()
  versions_str = " ".join(release.version for release in releases)
  print(versions_str)


def install(
    version_to_install: str,
    download_dir: pathlib.Path,
    install_dir: pathlib.Path,
    llvm_release_keys_file: pathlib.Path,
) -> None:
  logging.info("Installing clang-format version %s", version_to_install)
  releases = get_llvm_releases()
  releases_to_install = [release for release in releases if release.version == version_to_install]

  if len(releases_to_install) == 0:
    raise ClangFormatVersionNotFoundError(
        f"clang-format version not found: {version_to_install} (error code bef3e5b3ap)"
    )
  elif len(releases_to_install) > 1:
    raise MultipleClangFormatVersionsFoundError(
        f"{len(releases_to_install)} clang-format versions found "
        f"for version {version_to_install}, but expected exactly 1"
        " (error code gcn7ebjkj3)"
    )
  release_to_install = releases_to_install[0]

  uname = platform.uname()
  match (uname.system.lower(), uname.machine.lower()):
    case ("linux", "x86_64"):
      asset_name_suffix = "Linux-X64.tar.xz"
    case (unknown_system, unknown_machine):
      raise UnsupportedPlatformError(
          f"unsupported platform: system={unknown_system} machine={unknown_machine}"
          " (error code fvwnvmtmav)"
      )
  asset_name = "LLVM-" + version_to_install + "-" + asset_name_suffix

  signature_downloader = AssetDownloader(
      asset=asset_with_name(release_to_install.assets, asset_name + ".sig"),
      dest_file=download_dir / (asset_name + ".sig"),
  )
  signature_downloader.download()

  tarxz_downloader = AssetDownloader(
      asset=asset_with_name(release_to_install.assets, asset_name),
      dest_file=download_dir / asset_name,
      signature_file=signature_downloader.dest_file,
      public_keys_file=llvm_release_keys_file,
  )
  tarxz_downloader.download_if_needed_and_verify_pgp_signature()

  clang_format_file = download_dir / "clang-format"
  tarxz_file = tarxz_downloader.dest_file
  logging.info("Extracting clang-format from %s to %s", tarxz_file, clang_format_file)
  with tarfile.open(tarxz_file, "r:xz") as tar_file:
    clang_format_tar_infos: list[tarfile.TarInfo] = []
    for tar_info in tar_file:
      if not tar_info.isfile():
        continue
      tar_info_path = pathlib.PurePosixPath(tar_info.name)
      if tar_info_path.name != "clang-format":
        continue
      clang_format_tar_infos.append(tar_info)

  for tar_info in clang_format_tar_infos:
    logging.info("Extracting %s from %s to %s", tar_info.name, tarxz_file, clang_format_file)


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


def asset_with_name(assets: Sequence[LlvmReleaseAsset], name: str) -> LlvmReleaseAsset:
  found_assets: list[LlvmReleaseAsset] = [asset for asset in assets if asset.name == name]
  match len(found_assets):
    case 0:
      all_asset_names = ", ".join(sorted(asset.name for asset in assets))
      raise AssetNotFoundError(
          f"asset not found: {name} "
          f"(existing asset names: {all_asset_names})"
          "(error code pmc65927rm)"
      )
    case 1:
      return found_assets[0]
    case num_found_assets:
      raise MultipleAssetsFoundError(
          f"found {num_found_assets} assets with name {name}, "
          "but expected exactly 1"
          "(error code p7fta9kgv4)"
      )


class AssetDownloader:

  def __init__(
      self,
      asset: LlvmReleaseAsset,
      dest_file: pathlib.Path,
      signature_file: pathlib.Path | None = None,
      public_keys_file: pathlib.Path | None = None,
  ) -> None:
    self.asset = asset
    self.dest_file = dest_file
    self.signature_file = signature_file
    self.public_keys_file = public_keys_file

  def download(self) -> None:
    self._download(self.asset, self.dest_file)

  def download_if_needed_and_verify_pgp_signature(self) -> None:
    asset = self.asset
    dest_file = self.dest_file

    if not dest_file.exists():
      self.download_and_verify_pgp_signature()
      return

    logging.info(
        "Previously-downloaded file %s exists; verifying that it is the expected size (%s bytes)",
        dest_file,
        f"{asset.size:,}",
    )

    try:
      stat_result = dest_file.stat()
    except OSError as e:
      logging.warning(
          "Unable to determine size of previously-downloaded file %s: %s; re-downloading",
          dest_file,
          e.strerror,
      )
      self.download_and_verify_pgp_signature()
      return

    if stat_result.st_size != asset.size:
      logging.warning(
          "Previously-downloaded file %s has size %s bytes, "
          "but expected %s bytes; re-downloading it",
          dest_file,
          f"{stat_result.st_size:,}",
          f"{asset.size:,}",
      )
      self.download_and_verify_pgp_signature()
      return

    try:
      self.verify_pgp_signature()
    except self.SignatureVerificationError as e:
      logging.warning(
          "Failed to verify signature of previously-downloaded file %s: " "%s; re-downloading",
          dest_file,
          e,
      )
    else:
      # Signature verification successful; nothing to do, so return as if successful.
      return

    self.download_and_verify_pgp_signature()

  def download_and_verify_pgp_signature(self) -> None:
    self._download(self.asset, self.dest_file)
    self.verify_pgp_signature()

  def verify_pgp_signature(self) -> None:
    file_to_verify = self.dest_file
    signature_file = self.signature_file
    public_keys_file = self.public_keys_file

    if signature_file is None:
      raise ValueError("cannot verify PGP signature because self.signature_file is None")

    self._verify_pgp_signature(
        file_to_verify=file_to_verify,
        signature_file=signature_file,
        public_keys_file=public_keys_file,
    )

  @classmethod
  def _download(cls, asset: LlvmReleaseAsset, dest_file: pathlib.Path) -> None:
    download_url = asset.download_url
    download_num_bytes = asset.size

    logging.info(
        "Downloading %s (%s bytes) to %s",
        download_url,
        f"{download_num_bytes:,}",
        dest_file,
    )
    if download_num_bytes < 0:
      raise Exception(
          f"invalid download_num_bytes: {download_num_bytes:,} " "(error code px5e9pqbaz)"
      )

    dest_file.parent.mkdir(parents=True, exist_ok=True)

    current_progress_bar_context_manager = tqdm.tqdm(
        total=download_num_bytes,
        leave=False,
        unit=" bytes",
        dynamic_ncols=True,
    )
    with current_progress_bar_context_manager as current_progress_bar:
      with requests.get(download_url, stream=True) as response:
        response.raise_for_status()
        downloaded_num_bytes = 0
        with dest_file.open("wb") as output_file:
          for chunk in response.iter_content(chunk_size=65536):
            downloaded_num_bytes += len(chunk)
            if downloaded_num_bytes > download_num_bytes:
              raise cls.TooManyBytesDownloadedError(
                  f"Downloaded {downloaded_num_bytes:,} bytes from {download_url}, "
                  f"which is {downloaded_num_bytes - download_num_bytes:,} bytes more "
                  f"than expected ({download_num_bytes:,}) "
                  "(error code cv7fp9jb2e)"
              )

            output_file.write(chunk)
            current_progress_bar.update(len(chunk))

        if downloaded_num_bytes != download_num_bytes:
          raise cls.TooFewBytesDownloadedError(
              f"Downloaded {downloaded_num_bytes:,} bytes from {download_url}, "
              f"which is {download_num_bytes - downloaded_num_bytes:,} bytes fewer "
              f"than expected ({download_num_bytes:,}) "
              "(error code rf4n374kdm)"
          )

  @classmethod
  def _verify_pgp_signature(
      cls,
      file_to_verify: pathlib.Path,
      signature_file: pathlib.Path,
      public_keys_file: pathlib.Path | None,
  ) -> None:
    logging.info(
        "Verifying signature of file %s using signature from file %s",
        file_to_verify,
        signature_file,
    )
    with tempfile.TemporaryDirectory() as temp_gnupg_home_dir:
      gpg = gnupg.GPG(gnupghome=temp_gnupg_home_dir)

      if public_keys_file is not None:
        gpg.import_keys_file(str(public_keys_file))

      with signature_file.open("rb") as signature_file_stream:
        verified = gpg.verify_file(signature_file_stream, str(file_to_verify))

    if not verified:
      if verified.stderr:
        logging.warning("gnupg error output: %s", verified.stderr)
      statuses = ", ".join(
          str(problem["status"]) for problem in verified.problems if "status" in problem
      )
      raise cls.SignatureVerificationError(
          f"Verifying PGP signature of {file_to_verify} failed: {statuses}"
      )

  class TooManyBytesDownloadedError(Exception):
    pass

  class TooFewBytesDownloadedError(Exception):
    pass

  class SignatureVerificationError(Exception):
    pass


class AssetNotFoundError(Exception):
  pass


class MultipleAssetsFoundError(Exception):
  pass


class ClangFormatVersionNotFoundError(Exception):
  pass


class MultipleClangFormatVersionsFoundError(Exception):
  pass


class UnsupportedPlatformError(Exception):
  pass


if __name__ == "__main__":
  main()
