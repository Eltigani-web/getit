class Getit < Formula
  include Language::Python::Virtualenv

  desc "Universal file hosting downloader with TUI - GoFile, PixelDrain, MediaFire, 1Fichier, Mega.nz"
  homepage "https://github.com/yourusername/getit"
  url "https://files.pythonhosted.org/packages/source/g/getit/getit-0.1.0.tar.gz"
  sha256 "PLACEHOLDER_SHA256"
  license "MIT"

  depends_on "python@3.11"

  resource "aiohttp" do
    url "https://files.pythonhosted.org/packages/source/a/aiohttp/aiohttp-3.9.5.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "aiofiles" do
    url "https://files.pythonhosted.org/packages/source/a/aiofiles/aiofiles-24.1.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "typer" do
    url "https://files.pythonhosted.org/packages/source/t/typer/typer-0.12.3.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/source/r/rich/rich-13.7.1.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "textual" do
    url "https://files.pythonhosted.org/packages/source/t/textual/textual-0.70.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "pydantic" do
    url "https://files.pythonhosted.org/packages/source/p/pydantic/pydantic-2.7.4.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/source/p/pyyaml/PyYAML-6.0.1.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "beautifulsoup4" do
    url "https://files.pythonhosted.org/packages/source/b/beautifulsoup4/beautifulsoup4-4.12.3.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "pycryptodomex" do
    url "https://files.pythonhosted.org/packages/source/p/pycryptodomex/pycryptodomex-3.20.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "getit", shell_output("#{bin}/getit --version")
  end
end
