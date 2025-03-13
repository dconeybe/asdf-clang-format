from __future__ import annotations

from collections.abc import Sequence
import dataclasses
import logging
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import typing

from .argument_parser import ArgumentParser, ListAllCommand, DownloadCommand, InstallCommand
from .tempdir import TempDirFactory

import requests
import tqdm


def main() -> None:
  arg_parser = ArgumentParser()
  parsed_args = arg_parser.parse()

  logging.basicConfig(level=parsed_args.log_level)
  logger = logging.getLogger()

  match parsed_args.command:
    case ListAllCommand():
      list_all(logger=logger)
    case DownloadCommand() as command:
      download(
        clang_format_version=command.clang_format_version,
        download_dir=command.download_dir,
        stop_after_verify=command.stop_after == DownloadCommand.StopAfter.VERIFY,
        temp_dir_factory=parsed_args.temp_dir_factory,
        logger=logger,
      )
    case InstallCommand() as command:
      install(
        clang_format_version=command.clang_format_version,
        download_dir=command.download_dir,
        install_dir=command.install_dir,
        logger=logger,
      )


def list_all(logger: logging.Logger) -> None:
  releases = get_llvm_github_releases(logger)

  versions: list[str] = []
  for release in releases:
    artifacts = llvm_release_artifacts_from_llvm_github_release_assets(
      llvm_version=release.version,
      assets=release.assets,
    )

    try:
      artifact_for_current_platform_from_llvm_release_artifacts(artifacts)
    except (ArtifactNotFoundError, MultipleArtifactsFoundError):
      continue

    versions.append(release.version)

  print(" ".join(versions))


def download(
  clang_format_version: str,
  download_dir: pathlib.Path,
  stop_after_verify: bool,
  temp_dir_factory: TempDirFactory,
  logger: logging.Logger,
) -> None:
  logger.info("Downloading clang-format version %s", clang_format_version)
  artifact = get_llvm_github_artifact_for_current_platform(clang_format_version, logger)

  temp_dir = temp_dir_factory.get(f"v{clang_format_version}")

  signature_file_name = pathlib.PurePosixPath(artifact.signature_asset.name).name
  signature_downloader = AssetDownloader(
    asset=artifact.signature_asset,
    dest_file=temp_dir.path / signature_file_name,
    logger=logger,
  )
  signature_downloader.download()

  tarxz_file_name = pathlib.PurePosixPath(artifact.asset.name).name
  tarxz_downloader = AssetDownloader(
    asset=artifact.asset,
    dest_file=temp_dir.path / tarxz_file_name,
    signature_file=signature_downloader.dest_file,
    logger=logger,
  )
  tarxz_downloader.download_and_verify_sigstore_signature(clang_format_version)

  if stop_after_verify:
    logging.info("Stopping after verifying the signature of %s, as requested", tarxz_file_name)
    return

  downloaded_clang_format_file = untar_single_file(
    tarxz_file=tarxz_downloader.dest_file,
    dest_dir=temp_dir.subdir("clang_format_bin"),
    file_name="clang-format",
    estimated_num_entries=11000,
    logger=logger,
  )

  installed_clang_format_file = download_dir / "clang-format"
  logger.info(
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
  logger: logging.Logger,
) -> None:
  logger.info("Installing clang-format version %s", clang_format_version)

  src_file = download_dir / "clang-format"
  if not src_file.exists():
    raise DownloadedFileNotFoundError(f"file not found: {src_file} (error code vagvf88aer)")

  dest_file = install_dir / "bin" / "clang-format"
  logger.info("Copying %s to %s", src_file, dest_file)

  dest_file.parent.mkdir(parents=True, exist_ok=True)
  shutil.copy2(src_file, dest_file)


@dataclasses.dataclass(frozen=True)
class GitHubReleaseAsset:
  name: str
  size: int
  download_url: str


@dataclasses.dataclass(frozen=True)
class GitHubReleaseInfo:
  version: str
  assets: Sequence[GitHubReleaseAsset]


def get_llvm_github_releases(logger: logging.Logger) -> list[GitHubReleaseInfo]:
  url = "https://api.github.com/repos/llvm/llvm-project/releases"
  headers = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  }
  logger.info("Getting releases from %s", url)

  response = requests.get(url, headers=headers)
  response.raise_for_status()
  releases = response.json()

  llvm_release_infos: list[GitHubReleaseInfo] = []
  for release in releases:
    release_name = release["name"]
    version = release_name[5:]

    llvm_release_assets: list[GitHubReleaseAsset] = []
    assets = release.get("assets", [])
    if assets:
      for asset in assets:
        llvm_release_assets.append(
          GitHubReleaseAsset(
            name=asset["name"],
            size=asset["size"],
            download_url=asset["browser_download_url"],
          )
        )

    llvm_release_infos.append(GitHubReleaseInfo(version=version, assets=llvm_release_assets))

  return llvm_release_infos


def get_llvm_github_release(version: str, logger: logging.Logger) -> GitHubReleaseInfo:
  releases = get_llvm_github_releases(logger)
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


@dataclasses.dataclass(frozen=True)
class LlvmReleaseArtifact:
  operating_system: str
  cpu_architecture: str
  asset: GitHubReleaseAsset
  signature_asset: GitHubReleaseAsset


def get_llvm_github_artifact_for_current_platform(
  version: str, logger: logging.Logger
) -> LlvmReleaseArtifact:
  release = get_llvm_github_release(version, logger)
  artifacts = llvm_release_artifacts_from_llvm_github_release_assets(
    llvm_version=release.version,
    assets=release.assets,
  )
  return artifact_for_current_platform_from_llvm_release_artifacts(artifacts)


def llvm_release_artifacts_from_llvm_github_release_assets(
  llvm_version: str,
  assets: Sequence[GitHubReleaseAsset],
) -> list[LlvmReleaseArtifact]:
  tarball_regex = re.compile(
    re.escape(f"LLVM-{llvm_version}-") + r"(\w+)-(\w+)" + re.escape(".tar.xz")
  )
  signature_regex = re.compile(
    re.escape(f"LLVM-{llvm_version}-") + r"(\w+)-(\w+)" + re.escape(".tar.xz.jsonl")
  )

  tarballs: dict[tuple[str, str], GitHubReleaseAsset] = {}
  signatures: dict[tuple[str, str], GitHubReleaseAsset] = {}
  for asset in assets:
    tarball_match = tarball_regex.fullmatch(asset.name)
    signature_match = signature_regex.fullmatch(asset.name)
    if tarball_match is not None and signature_match is None:
      dest_dict = tarballs
      match = tarball_match
    elif tarball_match is None and signature_match is not None:
      dest_dict = signatures
      match = signature_match
    elif tarball_match is None and signature_match is None:
      continue
    else:
      raise Exception(
        "internal error e4bpy4jjmz: both tarball_match and signature_match are not None, "
        "but at most one of them should be not None: "
        f"tarball_match={tarball_match!r} signature_match={signature_match!r}"
      )

    os = match.group(1).lower()
    arch = match.group(2).lower()
    dest_dict[(os, arch)] = asset

  artifacts: list[LlvmReleaseArtifact] = []
  for key, tarball_asset in tarballs.items():
    if (signature_asset := signatures.get(key)) is None:
      # Ignore artifacts that lack a corresponding sigstore bundle,
      # as without it the authenticity cannot be verified.
      continue

    artifacts.append(
      LlvmReleaseArtifact(
        operating_system=key[0],
        cpu_architecture=key[1],
        asset=tarball_asset,
        signature_asset=signature_asset,
      )
    )

  return artifacts


def artifact_for_current_platform_from_llvm_release_artifacts(
  artifacts: Sequence[LlvmReleaseArtifact],
) -> LlvmReleaseArtifact:
  platform = llvm_os_arch_for_current_platform()
  matching_artifacts = [
    artifact
    for artifact in artifacts
    if (artifact.operating_system, artifact.cpu_architecture) == platform
  ]

  match len(matching_artifacts):
    case 0:
      raise ArtifactNotFoundError(
        f"no artifact found for current platform: {platform} (error code akkf4cpkep)"
      )
    case 1:
      return matching_artifacts[0]
    case num_matching_artifacts:
      raise MultipleArtifactsFoundError(
        f"{num_matching_artifacts} artifacts found for current platform {platform}, "
        "but expected exactly 1 (error code g5d36np3ps)"
      )


def llvm_os_arch_for_current_platform() -> tuple[str, str]:
  uname_result = platform.uname()

  match (uname_result.system.lower(), uname_result.machine.lower()):
    case ("linux", "x86_64"):
      return ("linux", "x64")
    case ("darwin", "arm64"):
      return ("macos", "arm64")
    case (unknown_system, unknown_machine):
      raise UnsupportedPlatformError(
        f"unknown platform: system={unknown_system} machine={unknown_machine} "
        "(error code fvwnvmtmav)"
      )


def untar_single_file(
  tarxz_file: pathlib.Path,
  dest_dir: pathlib.Path,
  file_name: str,
  estimated_num_entries: int,
  logger: logging.Logger,
) -> pathlib.Path:
  logger.info("Extracting %s from %s to %s", file_name, tarxz_file, dest_dir)

  logger.info("Searching for %s in %s", file_name, tarxz_file)

  # TODO: remove the typing cruft below once pyright recognizes the "r|xz" argument;
  # at the time of writing, it doesn't recognize these "streaming" modes, but only
  # the basic modes, like "r:xz".
  tar_file = tarfile.open(  # pyright: ignore[reportUnknownVariableType,reportCallIssue]
    tarxz_file,
    "r|xz",  # pyright: ignore[reportArgumentType]
  )

  progress_bar_context_manager = tqdm.tqdm(
    desc=f"Extracting {file_name}",
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

      progress_bar.clear()
      logger.info("Found %s in %s: %s", file_name, tarxz_file, tar_info.name)
      progress_bar.refresh()
      matching_tar_infos.append(tar_info)
      if len(matching_tar_infos) > 1:
        continue  # The error will be reported later on.

      dest_file = dest_dir / tar_info.name
      progress_bar.clear()
      logger.info("Extracting %s from %s to %s", tar_info.name, tarxz_file, dest_file)
      progress_bar.refresh()
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


class ArtifactNotFoundError(Exception):
  pass


class MultipleArtifactsFoundError(Exception):
  pass


class FileNotFoundInTarFileError(Exception):
  pass


class MultipleFilesFoundInTarFileError(Exception):
  pass


class AssetDownloader:
  def __init__(
    self,
    asset: GitHubReleaseAsset,
    dest_file: pathlib.Path,
    logger: logging.Logger,
    signature_file: pathlib.Path | None = None,
  ) -> None:
    self.asset = asset
    self.dest_file = dest_file
    self.signature_file = signature_file
    self.logger = logger

  def download(self) -> None:
    self._download(self.asset, self.dest_file, self.logger)

  def download_and_verify_sigstore_signature(self, llvm_version: str) -> None:
    self._download(self.asset, self.dest_file, self.logger)
    self.verify_sigstore_signature(llvm_version)

  def verify_sigstore_signature(self, llvm_version: str) -> None:
    file_to_verify = self.dest_file
    signature_file = self.signature_file

    if signature_file is None:
      raise ValueError("cannot verify sigstore signature because self.signature_file is None")

    self._verify_sigstore_signature(
      llvm_version=llvm_version,
      file_to_verify=file_to_verify,
      signature_file=signature_file,
      logger=self.logger,
    )

  @classmethod
  def _download(
    cls,
    asset: GitHubReleaseAsset,
    dest_file: pathlib.Path,
    logger: logging.Logger,
  ) -> None:
    download_url = asset.download_url
    download_num_bytes = asset.size

    logger.info(
      "Downloading %s (%s bytes) to %s",
      download_url,
      f"{download_num_bytes:,}",
      dest_file,
    )
    if download_num_bytes < 0:
      raise Exception(f"invalid download_num_bytes: {download_num_bytes:,} (error code px5e9pqbaz)")

    dest_file.parent.mkdir(parents=True, exist_ok=True)

    progress_bar_context_manager = tqdm.tqdm(
      desc="Downloading",
      total=download_num_bytes,
      leave=False,
      unit=" bytes",
      dynamic_ncols=True,
    )
    with progress_bar_context_manager as progress_bar:
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
            progress_bar.update(len(chunk))

        if downloaded_num_bytes != download_num_bytes:
          raise cls.TooFewBytesDownloadedError(
            f"Downloaded {downloaded_num_bytes:,} bytes from {download_url}, "
            f"which is {download_num_bytes - downloaded_num_bytes:,} bytes fewer "
            f"than expected ({download_num_bytes:,}) (error code rf4n374kdm)"
          )

  @classmethod
  def _verify_sigstore_signature(
    cls,
    llvm_version: str,
    file_to_verify: pathlib.Path,
    signature_file: pathlib.Path,
    logger: logging.Logger,
  ) -> None:
    logger.info(
      "Verifying signature of file %s using sigstore bundle from file %s",
      file_to_verify,
      signature_file,
    )

    cert_identity = (
      "https://github.com/llvm/llvm-project/"
      ".github/workflows/release-binaries.yml"
      f"@refs/tags/llvmorg-{llvm_version}"
    )

    sigstore_args: list[str] = [
      sys.executable,
      "-m",
      "sigstore",
      "verify",
      "github",
      "--bundle",
      str(signature_file),
      "--cert-identity",
      cert_identity,
      str(file_to_verify),
    ]

    if logger.isEnabledFor(logging.DEBUG):
      sigstore_args.append("--verbose")
      output_file = None
      stdout = None
      stderr = None
    elif logger.isEnabledFor(logging.INFO):
      output_file = None
      stdout = None
      stderr = None
    else:
      output_file = tempfile.TemporaryFile()
      stdout = output_file
      stderr = subprocess.STDOUT

    logging.info("Running command: {subprocess.list2cmdline(sigstore_args)}")
    sigstore_completed_process = subprocess.run(
      sigstore_args,
      stdout=stdout,
      stderr=stderr,
    )

    if sigstore_completed_process.returncode != 0:
      if output_file is not None:
        output_file.seek(0)
        # Limit the number of bytes read to avoid unbounded memory usage.
        stdout_bytes = output_file.read(131072)
        stdout_text = stdout_bytes.decode("utf8", errors="replace").strip()
        if stdout_text:
          logger.warning(stdout_text)

      raise cls.SignatureVerificationError(
        f"Verifying sigstore signature of {file_to_verify} failed: "
        f"command completed with non-zero exit code {sigstore_completed_process.returncode}: "
        + subprocess.list2cmdline(sigstore_args)
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
