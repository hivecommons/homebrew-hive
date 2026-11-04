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
      url "https://github.com/hivecommons/crux/releases/download/v0.3.0/crux_0.3.0_darwin_arm64.tar.gz"
      sha256 "459cf8ca44401fefc7676e2cd873656dcebc200d678d4de3a3ca6a31a7847e90"
    end
    on_intel do
      url "https://github.com/hivecommons/crux/releases/download/v0.3.0/crux_0.3.0_darwin_amd64.tar.gz"
      sha256 "37f16858770731e27fc8a2eecf68cacd40c93a0b23cba470a1dcfa8071ba10b9"
    end
  end

  on_linux do
    on_arm do
      url "https://github.com/hivecommons/crux/releases/download/v0.3.0/crux_0.3.0_linux_arm64.tar.gz"
      sha256 "560a7105facebf69662e3e9ff6c1651ea39b8dddb753b229f53d19eb22c0dd42"
    end
    on_intel do
      url "https://github.com/hivecommons/crux/releases/download/v0.3.0/crux_0.3.0_linux_amd64.tar.gz"
      sha256 "ea5e6651f626f6b962d2158fd0f188f0a10469c5ae8988349172d864acef4c6a"
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
    pid = spawn bin/"crux", "serve", "--socket", sock, out: log, err: [:child, :out]
    begin
      50.times do
        break if sock.exist?

        sleep 0.2
      end
      assert_predicate sock, :exist?, "crux serve did not create #{sock}:\n#{log.read}"
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
