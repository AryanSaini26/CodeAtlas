class Codeatlas < Formula
  include Language::Python::Virtualenv

  desc "MCP server that constructs real-time code knowledge graphs for AI coding agents"
  homepage "https://github.com/AryanSaini26/CodeAtlas"
  url "https://files.pythonhosted.org/packages/source/c/codeatlas/codeatlas-1.0.0.tar.gz"
  sha256 "REPLACE_WITH_SDIST_SHA256_AFTER_PYPI_PUBLISH"
  license "MIT"
  head "https://github.com/AryanSaini26/CodeAtlas.git", branch: "main"

  depends_on "python@3.12"
  depends_on "rust" => :build

  def install
    venv = virtualenv_create(libexec, "python3.12")
    system libexec/"bin/pip", "install", "-v",
           "--no-deps", "--no-binary", ":none:",
           "--ignore-installed",
           buildpath
    system libexec/"bin/pip", "install", "-v",
           "codeatlas[all]==#{version}"
    (bin/"codeatlas").write_env_script libexec/"bin/codeatlas", PATH: "#{libexec}/bin:$PATH"
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/codeatlas --version")

    (testpath/"hello.py").write <<~EOS
      def greet(name: str) -> str:
          return f"hello {name}"
    EOS

    system bin/"codeatlas", "init", "--db", "#{testpath}/graph.db"
    system bin/"codeatlas", "index", "--db", "#{testpath}/graph.db", testpath
    stats = shell_output("#{bin}/codeatlas stats --db #{testpath}/graph.db")
    assert_match "greet", stats
  end
end
