# frozen_string_literal: true

class Getit < Formula
  desc "Universal file hosting downloader with TUI"
  homepage "https://github.com/Eltigani-web/getit"
  url "https://files.pythonhosted.org/packages/py3/g/getit-cli/getit_cli-{{VERSION}}-py3-none-any.whl"
  sha256 "{{SHA256}}"
  license "GPL-3.0-or-later"

  depends_on "python@3.11"
  depends_on "py3-pip"

  def install
    system "pip3", "install", "--prefix=#{prefix}",
           "--no-cache-dir", "--no-deps", cached_download

    bin.install Dir.glob("#{libexec}/bin/*")[0] => "getit"
  end

  test do
    system bin/"getit", "--version"
  end
end
