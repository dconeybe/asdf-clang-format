<div align="center">

# asdf-clang-format [![Build](https://github.com/dconeybe/asdf-clang-format/actions/workflows/build.yml/badge.svg)](https://github.com/dconeybe/asdf-clang-format/actions/workflows/build.yml) [![Lint](https://github.com/dconeybe/asdf-clang-format/actions/workflows/lint.yml/badge.svg)](https://github.com/dconeybe/asdf-clang-format/actions/workflows/lint.yml)

[clang-format](https://github.com/dconeybe/asdf-clang-format) plugin for the [asdf version manager](https://asdf-vm.com).

</div>

# Contents

- [Dependencies](#dependencies)
- [Install](#install)
- [Contributing](#contributing)
- [License](#license)

# Dependencies

**TODO: adapt this section**

- `bash`, `curl`, `tar`, and [POSIX utilities](https://pubs.opengroup.org/onlinepubs/9699919799/idx/utilities.html).
- `SOME_ENV_VAR`: set this environment variable in your shell config to load the correct version of tool x.

# Install

Plugin:

```shell
asdf plugin add clang-format
# or
asdf plugin add clang-format https://github.com/dconeybe/asdf-clang-format.git
```

clang-format:

```shell
# Show all installable versions
asdf list-all clang-format

# Install specific version
asdf install clang-format latest

# Set a version globally (on your ~/.tool-versions file)
asdf global clang-format latest

# Now clang-format commands are available
clang-format --help
```

Check [asdf](https://github.com/asdf-vm/asdf) readme for more instructions on how to
install & manage versions.

# Contributing

Contributions of any kind welcome! See the [contributing guide](contributing.md).

[Thanks goes to these contributors](https://github.com/dconeybe/asdf-clang-format/graphs/contributors)!

# License

See [LICENSE](LICENSE) © [Denver Coneybeare](https://github.com/dconeybe/)
