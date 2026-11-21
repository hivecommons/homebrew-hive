cask "quorum-companion" do
  version "0.2.0"
  sha256 "1dc23bee85d8918c4f3ea5b9ac9cd17d4e04e6fe63d7e3026382bfa52592824b"

  url "https://github.com/hivecommons/quorum-companion/releases/download/v#{version}/QuorumCompanion-#{version}-macos-arm64.zip"
  name "Quorum Companion"
  desc "Lets hive's Betty listen to your own meeting app after you confirm consent"
  homepage "https://github.com/hivecommons/quorum-companion"

  livecheck do
    url :url
    strategy :github_latest
  end

  depends_on arch: :arm64
  depends_on macos: :sonoma

  app "Quorum Companion.app"

  zap trash: [
    "~/Library/Application Support/dev.hivecommons.quorum-companion",
    "~/Library/Caches/dev.hivecommons.quorum-companion",
    "~/Library/WebKit/dev.hivecommons.quorum-companion",
  ]

  caveats <<~EOS
    Quorum Companion is ad-hoc signed and not notarized (no Apple Developer ID).
    On first launch macOS blocks it: open System Settings, Privacy & Security,
    and click "Open Anyway" next to the message about Quorum Companion.

    When you first let Betty listen, allow Microphone and
    Screen & System Audio Recording. macOS may ask again after an update; see
    https://github.com/hivecommons/quorum-companion#install-macos

    Needs macOS 14.2 or later. Create a companion token on your hive at
    <hive URL>/companion/token, then paste the URL and token into Settings.
  EOS
end
