# typed: false
# frozen_string_literal: true

# Hand-maintained formula: not produced by scripts/generate-formula.py.
# See Formula/README.md for the ownership split and the release checklist.
class Crux < Formula
  desc "Governed AI agent runtime from Hive: run, observe and control agents"
  homepage "https://github.com/hivecommons/crux"
  license "Apache-2.0"

  depends_on "tmux"

  on_macos do
    on_arm do
      url "https://github.com/hivecommons/crux/releases/download/v0.4.0/crux_0.4.0_darwin_arm64.tar.gz"
      sha256 "bd993e96925fea9af154b3ac6542ccf50d284d353463f6fc5299a46d09f5dce6"
    end
    on_intel do
      url "https://github.com/hivecommons/crux/releases/download/v0.4.0/crux_0.4.0_darwin_amd64.tar.gz"
      sha256 "bd0bfdbc7c07c6bf7a6dee259e3ebc9a20c2cabd640e7a01f04ac466f0128a9b"
    end
  end

  on_linux do
    on_arm do
      url "https://github.com/hivecommons/crux/releases/download/v0.4.0/crux_0.4.0_linux_arm64.tar.gz"
      sha256 "72891231317a88017c6150a8c1f0460519527f616fe20aaed0e43635c28dec66"
    end
    on_intel do
      url "https://github.com/hivecommons/crux/releases/download/v0.4.0/crux_0.4.0_linux_amd64.tar.gz"
      sha256 "45f5de136f92053a0245cc723e15c80fb324060c48e79589e30a8859ee2e3eb0"
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
    log = testpath/"serve.log"
    pid = spawn bin/"crux", "serve", "--socket", sock, out: log.to_s, err: [:child, :out]
    begin
      50.times do
        break if sock.exist?

        sleep 0.2
      end
      assert_path_exists sock, "crux serve did not create #{sock}:\n#{log.read}"
      assert_match "NAME", shell_output("#{bin}/crux --server #{sock} ps")
    ensure
      begin
        Process.kill("INT", pid)
      rescue Errno::ESRCH
        # The server may have exited before creating its socket.
      end
      Process.wait(pid)
    end
  end
end
