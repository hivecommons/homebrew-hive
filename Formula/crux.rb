# typed: false
# frozen_string_literal: true

# Hand-maintained formula: not produced by scripts/generate-formula.py.
# See Formula/README.md for the ownership split and the release checklist.
class Crux < Formula
  desc "Governed AI agent runtime from Hive: run, observe and control agents"
  homepage "https://github.com/hivecommons/crux"
  version "0.1.0"
  license "Apache-2.0"

  depends_on "tmux"

  on_macos do
    on_arm do
      url "https://github.com/hivecommons/crux/releases/download/v#{version}/crux_#{version}_darwin_arm64.tar.gz"
      sha256 "21e94af87cdae022ced1f1addd3a52601b159e25a444d1f1b4c35988a15b7416"
    end
    on_intel do
      url "https://github.com/hivecommons/crux/releases/download/v#{version}/crux_#{version}_darwin_amd64.tar.gz"
      sha256 "027b06ff09c1284871e485413a245b5a55d37653d81327e65ba9953dccc79001"
    end
  end

  on_linux do
    on_arm do
      url "https://github.com/hivecommons/crux/releases/download/v#{version}/crux_#{version}_linux_arm64.tar.gz"
      sha256 "aaefd87f6def57e2d82d0e8dc4488cac02a6a45f115b2e32cdac937a8b80f993"
    end
    on_intel do
      url "https://github.com/hivecommons/crux/releases/download/v#{version}/crux_#{version}_linux_amd64.tar.gz"
      sha256 "59c3d1d2f04e92341903c460bccf3111d1ad39b7a7b03469b0cbd662b387ae25"
    end
  end

  def install
    bin.install "crux"
  end

  def caveats
    <<~EOS
      The code behind this binary lives in hivecommons/hive (src/crux);
      hivecommons/crux is a synced, module-path-rewritten copy. File issues
      and pull requests in hivecommons/hive.

        crux serve --socket /tmp/crux.sock
        crux --server /tmp/crux.sock ps
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/crux --version")
    sock = testpath/"s.sock"
    pid = spawn bin/"crux", "serve", "--socket", sock
    begin
      50.times do
        break if sock.exist?

        sleep 0.2
      end
      assert_match "NAME", shell_output("#{bin}/crux --server #{sock} ps")
    ensure
      Process.kill("INT", pid)
      Process.wait(pid)
    end
  end
end
