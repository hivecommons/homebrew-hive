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
      url "https://github.com/hivecommons/crux/releases/download/v0.2.0/crux_0.2.0_darwin_arm64.tar.gz"
      sha256 "0c4bb10b929c0c0bad7d1cf9e00757663df20817e667fc8f1c64ce23290ae01e"
    end
    on_intel do
      url "https://github.com/hivecommons/crux/releases/download/v0.2.0/crux_0.2.0_darwin_amd64.tar.gz"
      sha256 "1919e2544319bdb5929186d0431be715b49b455318591500cac2836535977425"
    end
  end

  on_linux do
    on_arm do
      url "https://github.com/hivecommons/crux/releases/download/v0.2.0/crux_0.2.0_linux_arm64.tar.gz"
      sha256 "2a2d784bf649a04f61fbaea5342531ba2f747fc615a7cc863ad68b2942381226"
    end
    on_intel do
      url "https://github.com/hivecommons/crux/releases/download/v0.2.0/crux_0.2.0_linux_amd64.tar.gz"
      sha256 "c8e03218f51dccd6396f04011af81e137614e9b727a21c82d68c4fdb435b0d16"
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
