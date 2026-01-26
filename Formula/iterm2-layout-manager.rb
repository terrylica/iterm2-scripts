class Iterm2LayoutManager < Formula
  include Language::Python::Virtualenv

  desc "iTerm2 workspace automation with split panes"
  homepage "https://github.com/terrylica/iterm2-scripts"
  url "https://github.com/terrylica/iterm2-scripts/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "PLACEHOLDER_SHA256"
  license "MIT"

  depends_on "python@3.11"

  # Auto-generated via: brew update-python-resources iterm2-layout-manager
  # resource "iterm2" do
  #   url "https://files.pythonhosted.org/packages/.../iterm2-2.7.tar.gz"
  #   sha256 "..."
  # end

  # resource "pyobjc-core" do
  #   url "https://files.pythonhosted.org/packages/.../pyobjc_core-10.0.tar.gz"
  #   sha256 "..."
  # end

  # resource "loguru" do
  #   url "https://files.pythonhosted.org/packages/.../loguru-0.7.2.tar.gz"
  #   sha256 "..."
  # end

  # resource "platformdirs" do
  #   url "https://files.pythonhosted.org/packages/.../platformdirs-4.2.0.tar.gz"
  #   sha256 "..."
  # end

  # Livecheck: Auto-detect new versions from GitHub releases
  livecheck do
    url :stable
    regex(/v?(\d+(?:\.\d+)+)$/i)
    strategy :github_releases
  end

  def install
    # Install main script
    libexec.install "default-layout.py"
    libexec.install "claude-orphan-cleanup.py"
    libexec.install "layout.example.toml"
    libexec.install "setup.sh"
    
    # Install bin utilities
    (libexec/"bin").install Dir["bin/*"]
    
    # Install shell completions
    zsh_completion.install "completions/_iterm2-layout"
    bash_completion.install "completions/iterm2-layout.bash"

    # Create wrapper script that calls setup
    bin.install "setup.sh" => "iterm2-layout-setup"
  end

  def post_install
    require "fileutils"

    # Target directory for iTerm2 AutoLaunch
    auto_launch_dir = "#{ENV['HOME']}/Library/Application Support/iTerm2/Scripts/AutoLaunch"
    script_path = "#{auto_launch_dir}/default-layout.py"

    # Create directory if needed
    FileUtils.mkdir_p(auto_launch_dir)

    # Conflict detection: Check for existing files
    if File.exist?(script_path) && !File.symlink?(script_path)
      opoo "Existing file found at #{script_path}"
      opoo "Backing up to #{script_path}.bak"
      FileUtils.mv(script_path, "#{script_path}.bak")
    elsif File.symlink?(script_path)
      current_target = File.readlink(script_path)
      unless current_target.include?("iterm2-layout-manager")
        opoo "Existing symlink points to: #{current_target}"
        FileUtils.rm_f(script_path)
      end
    end

    # Create symlink to installed script
    FileUtils.ln_sf("#{libexec}/default-layout.py", script_path)
    ohai "Created AutoLaunch symlink: #{script_path}"
  end

  def caveats
    <<~EOS
      Setup complete! Enable Python API in iTerm2:
        iTerm2 → Settings → General → Magic → Enable Python API

      Then restart iTerm2.

      To uninstall completely:
        rm -f ~/Library/Application\\ Support/iTerm2/Scripts/AutoLaunch/default-layout.py
        brew uninstall iterm2-layout-manager

      Shell completions have been installed for zsh and bash.
    EOS
  end

  test do
    # Test Python script is installed
    assert_predicate libexec/"default-layout.py", :exist?
  end
end
