import argparse
from collections.abc import Sequence
import dataclasses
import logging
import pathlib
import platform
import shutil
import sys
import tarfile
import tempfile
import typing

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

  install_subparser = subparsers.add_parser("download")
  install_subparser.set_defaults(command="download")
  install_subparser.add_argument("--clang-format-version", required=True)
  install_subparser.add_argument("--download-dir", required=True)
  install_subparser.add_argument("--llvm-release-keys-file", required=True)

  install_subparser = subparsers.add_parser("install")
  install_subparser.set_defaults(command="install")
  install_subparser.add_argument("--clang-format-version", required=True)
  install_subparser.add_argument("--download-dir", required=True)
  install_subparser.add_argument("--install-dir", required=True)

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
    case "download":
      clang_format_version = parsed_args.clang_format_version
      download_dir = pathlib.Path(parsed_args.download_dir)
      llvm_release_keys_file = pathlib.Path(parsed_args.llvm_release_keys_file)
      download(
          clang_format_version=clang_format_version,
          download_dir=download_dir,
          llvm_release_keys_file=llvm_release_keys_file,
      )
    case "install":
      clang_format_version = parsed_args.clang_format_version
      download_dir = pathlib.Path(parsed_args.download_dir)
      install_dir = pathlib.Path(parsed_args.install_dir)
      install(
          clang_format_version=clang_format_version,
          download_dir=download_dir,
          install_dir=install_dir,
      )
    case unknown_command:
      raise Exception(f"internal error ysnynaqa84: unknown command: {unknown_command}")


def list_all() -> None:
  releases = get_llvm_releases()
  versions_str = " ".join(release.version for release in releases)
  print(versions_str)


def download(
    clang_format_version: str,
    download_dir: pathlib.Path,
    llvm_release_keys_file: pathlib.Path,
) -> None:
  logging.info("Downloading clang-format version %s", clang_format_version)
  asset_name_platform = llvm_release_asset_name_platform_component()
  asset_name = "LLVM-" + clang_format_version + "-" + asset_name_platform + ".tar.xz"

  # Keep a hard reference to the TemporaryDirectory object so that it does not
  # get cleaned up until it is no longer needed.
  temporary_directory = tempfile.TemporaryDirectory()
  temp_dir = pathlib.Path(temporary_directory.name)

  llvm_release = get_llvm_release(clang_format_version)

  signature_downloader = AssetDownloader(
      asset=asset_with_name(llvm_release.assets, asset_name + ".sig"),
      dest_file=temp_dir / (asset_name + ".sig"),
  )
  signature_downloader.download()

  tarxz_downloader = AssetDownloader(
      asset=asset_with_name(llvm_release.assets, asset_name),
      dest_file=temp_dir / asset_name,
      signature_file=signature_downloader.dest_file,
      public_keys_file=llvm_release_keys_file,
  )
  tarxz_downloader.download_and_verify_pgp_signature()

  downloaded_clang_format_file = untar_single_file(
      tarxz_file=tarxz_downloader.dest_file,
      dest_dir=pathlib.Path(tempfile.mkdtemp(dir=temp_dir)),
      file_name="clang-format",
      estimated_num_entries=11000,
  )

  installed_clang_format_file = download_dir / "clang-format"
  logging.info(
      "Moving %s to %s",
      downloaded_clang_format_file,
      installed_clang_format_file,
  )
  installed_clang_format_file.parent.mkdir(parents=True, exist_ok=True)
  shutil.move(downloaded_clang_format_file, installed_clang_format_file)


def install(
    clang_format_version: str,
    download_dir: pathlib.Path,
    install_dir: pathlib.Path,
) -> None:
  logging.info("Installing clang-format version %s", clang_format_version)

  src_file = download_dir / "clang-format"
  if not src_file.exists():
    raise DownloadedFileNotFoundError(f"file not found: {src_file} (error code vagvf88aer)")

  dest_file = install_dir / "bin" / "clang-format"
  logging.info("Copying %s to %s", src_file, dest_file)

  dest_file.parent.mkdir(parents=True, exist_ok=True)
  shutil.copy2(src_file, dest_file)


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


def get_llvm_release(version: str) -> LlvmReleaseInfo:
  releases = get_llvm_releases()
  releases_with_desired_version = [release for release in releases if release.version == version]

  match len(releases_with_desired_version):
    case 0:
      raise ClangFormatVersionNotFoundError(
          f"clang-format version not found: {version} (error code bef3e5b3ap)"
      )
    case 1:
      return releases_with_desired_version[0]
    case num_versions_found:
      raise MultipleClangFormatVersionsFoundError(
          f"{num_versions_found} clang-format versions found "
          f"for version {version}, but expected exactly 1 "
          "(error code gcn7ebjkj3)"
      )


def asset_with_name(assets: Sequence[LlvmReleaseAsset], name: str) -> LlvmReleaseAsset:
  found_assets: list[LlvmReleaseAsset] = [asset for asset in assets if asset.name == name]
  match len(found_assets):
    case 0:
      all_asset_names = ", ".join(sorted(asset.name for asset in assets))
      raise AssetNotFoundError(
          f"asset not found: {name} "
          f"(existing asset names: {all_asset_names}) "
          "(error code pmc65927rm)"
      )
    case 1:
      return found_assets[0]
    case num_found_assets:
      raise MultipleAssetsFoundError(
          f"found {num_found_assets} assets with name {name}, "
          "but expected exactly 1 (error code p7fta9kgv4)"
      )


def llvm_release_asset_name_platform_component() -> str:
  uname_result = platform.uname()

  match (uname_result.system.lower(), uname_result.machine.lower()):
    case ("linux", "x86_64"):
      return "Linux-X64"
    case ("darwin", "arm64"):
      return "macOS-ARM64"
    case (unknown_system, unknown_machine):
      raise UnsupportedPlatformError(
          f"unsupported platform: system={unknown_system} machine={unknown_machine} "
          "(error code fvwnvmtmav)"
      )


def untar_single_file(
    tarxz_file: pathlib.Path,
    dest_dir: pathlib.Path,
    file_name: str,
    estimated_num_entries: int,
) -> pathlib.Path:
  logging.info("Extracting %s from %s to %s", file_name, tarxz_file, dest_dir)

  logging.info("Searching for %s in %s", file_name, tarxz_file)

  # TODO: remove the typing cruft below once pyright recognizes the "r|xz" argument;
  # at the time of writing, it doesn't recognize these "streaming" modes, but only
  # the basic modes, like "r:xz".
  tar_file = tarfile.open(  # pyright: ignore[reportUnknownVariableType,reportCallIssue]
      tarxz_file,
      "r|xz",  # pyright: ignore[reportArgumentType]
  )

  progress_bar_context_manager = tqdm.tqdm(
      total=estimated_num_entries,
      leave=False,
      unit=" files",
      dynamic_ncols=True,
  )

  tar_file = typing.cast(tarfile.TarFile, tar_file)
  with tar_file, progress_bar_context_manager as progress_bar:
    matching_tar_infos: list[tarfile.TarInfo] = []
    for tar_info in tar_file:
      progress_bar.update(1)
      if not tar_info.isfile():
        continue

      tar_info_path = pathlib.PurePosixPath(tar_info.name)
      if tar_info_path.name != file_name:
        continue

      logging.info("Found %s in %s: %s", file_name, tarxz_file, tar_info.name)
      matching_tar_infos.append(tar_info)
      if len(matching_tar_infos) > 1:
        continue  # The error will be reported later on.

      dest_file = dest_dir / tar_info.name
      logging.info("Extracting %s from %s to %s", tar_info.name, tarxz_file, dest_file)
      tar_file.extract(tar_info, dest_dir, filter="data")

  match len(matching_tar_infos):
    case 0:
      raise FileNotFoundInTarFileError(
          f"no file named {file_name} found in tar file: {tarxz_file} (error code j9ebr9gyhb)"
      )
    case 1:
      # It is safe to ignore the pyright typing error below as this code path can _only_ be
      # reached if `dest_file` has been bound.
      return dest_file  # pyright: ignore[reportPossiblyUnboundVariable]
    case num_files_found:
      raise MultipleFilesFoundInTarFileError(
          f"{num_files_found} files named {file_name} found in tar file {tarxz_file}, "
          "but expected exactly 1 (error code cstaaxdsn9)"
      )


class FileNotFoundInTarFileError(Exception):
  pass


class MultipleFilesFoundInTarFileError(Exception):
  pass


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
      raise Exception(f"invalid download_num_bytes: {download_num_bytes:,} (error code px5e9pqbaz)")

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
                  f"than expected ({download_num_bytes:,}) (error code cv7fp9jb2e)"
              )

            output_file.write(chunk)
            current_progress_bar.update(len(chunk))

        if downloaded_num_bytes != download_num_bytes:
          raise cls.TooFewBytesDownloadedError(
              f"Downloaded {downloaded_num_bytes:,} bytes from {download_url}, "
              f"which is {download_num_bytes - downloaded_num_bytes:,} bytes fewer "
              f"than expected ({download_num_bytes:,}) (error code rf4n374kdm)"
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


class DownloadedFileNotFoundError(Exception):
  pass


if __name__ == "__main__":
  main()
