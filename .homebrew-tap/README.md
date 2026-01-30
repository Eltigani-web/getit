# getit Homebrew Tap

This tap provides the [getit](https://github.com/Eltigani-web/getit) formula for macOS and Linux.

## Installation

### Install Homebrew
If you don't have Homebrew installed, follow the instructions at [brew.sh](https://brew.sh).

### Tap and install getit
```bash
brew tap Eltigani-web/getit
brew install getit
```

## Usage

After installation, you can use getit directly from your terminal:

```bash
getit --version
getit download https://gofile.io/d/abc123
getit tui
```

For comprehensive usage documentation, see the [getit README](https://github.com/Eltigani-web/getit).

## Development

### Update the formula

When releasing a new version of getit:

1. Update the version and sha256 in [Formula/getit.rb](Formula/getit.rb)
2. The version comes from git tags in the main repository
3. To get the sha256:
   ```bash
   curl -L https://files.pythonhosted.org/packages/py3/g/getit-cli/getit_cli-<VERSION>-py3-none-any.whl | shasum -a 256
   ```

### Test the formula locally

```bash
brew install --build-from-source Formula/getit.rb
```

## License

This tap and the getit formula are licensed under the GPL-3.0-or-later, matching the main project.

## Issues

For issues with the Homebrew formula, please open an issue in the [main getit repository](https://github.com/Eltigani-web/getit/issues).
