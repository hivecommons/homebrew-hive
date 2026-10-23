# typed: false
# frozen_string_literal: true

# Hand-maintained formula: not produced by scripts/generate-formula.py.
# See Formula/README.md for the ownership split and the release checklist.
class Hotshot < Formula
  desc "Screenshot-to-path menu-bar helper for AI coding terminals"
  homepage "https://github.com/hivecommons/hotshot"
  url "https://github.com/hivecommons/hotshot/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "f36518aa39dc3007367ea9525c7b1be3ee5af2b47aa44e41720224126aaccebe"
  license "Apache-2.0"

  depends_on xcode: ["15.0", :build]
  depends_on macos: :ventura

  def install
    system "swift", "build", "-c", "release", "--disable-sandbox"
    bin.install ".build/release/hotshot"
  end

  def caveats
    <<~EOS
      This formula installs only the `hotshot` command-line binary. Run it as

        hotshot &

      to start the menu-bar app; macOS asks for Accessibility permission the
      first time (System Settings > Privacy & Security). A double-clickable
      Hotshot.app bundle is not shipped by this formula: build one from a
      source checkout with `scripts/bundle.sh` (see the upstream README).
    EOS
  end

  test do
    # hotshot is a menu-bar app with no --version/--help flag; invoking it
    # starts an NSApplication run loop, which cannot run in a test sandbox.
    assert_predicate bin/"hotshot", :executable?
    assert_match "Mach-O", shell_output("file #{bin}/hotshot")
  end
end
