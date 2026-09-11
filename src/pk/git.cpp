#include "pk/git.hpp"

#include <charconv>

namespace pk::git {

const char kLogFormat[] = "--format=%x00%H%x00%P%x00%at%x00%an%x00%s";

namespace {

std::vector<std::string> base_argv(std::string_view repo) {
  return {"git", "-C", std::string(repo)};
}

// Options that stop a user's config from rewriting the stream under us. An
// external diff driver, a textconv filter or `color.ui = always` would each
// change what the parser sees. These go on the *indexing* commands only: the
// verification call must run exactly as the user's own `git log -S` would.
void append_safe_flags(std::vector<std::string>& argv) {
  argv.emplace_back("--no-color");
  argv.emplace_back("--no-ext-diff");
  argv.emplace_back("--no-textconv");
  argv.emplace_back("--no-notes");
  argv.emplace_back("--no-show-signature");
}

bool run(const std::vector<std::string>& argv, std::string_view input,
         const ChunkSink& sink, std::string& error) {
  Subprocess child;
  if (!child.start(argv, !input.empty())) {
    error = child.error();
    return false;
  }
  if (!child.pump(input, sink)) {
    error = child.error();
    child.wait();
    return false;
  }
  const int status = child.wait();
  if (status != 0) {
    std::string what = "git";  // argv[0..2] is always `git -C <repo>`
    for (std::size_t i = 3; i < argv.size() && i < 6; ++i) {
      what += ' ';
      what += argv[i];
    }
    error = what + (status < 0 ? " was killed by a signal"
                               : " exited with status " + std::to_string(status));
    return false;
  }
  return true;
}

bool run_lines(const std::vector<std::string>& argv, std::string_view input,
               const LineSplitter::LineSink& on_line, std::string& error) {
  LineSplitter splitter;
  const bool ok = run(
      argv, input,
      [&](std::string_view chunk) { splitter.feed(chunk, on_line); }, error);
  splitter.finish(on_line);
  return ok;
}

}  // namespace

bool rev_list_count(std::string_view repo, std::uint64_t& count, std::string& error) {
  std::vector<std::string> argv = base_argv(repo);
  argv.insert(argv.end(), {"rev-list", "--all", "--count"});

  std::string text;
  if (!run(argv, {}, [&](std::string_view chunk) { text.append(chunk); }, error)) {
    return false;
  }
  std::string_view digits = text;
  while (!digits.empty() && (digits.back() == '\n' || digits.back() == ' ')) {
    digits.remove_suffix(1);
  }
  const auto result =
      std::from_chars(digits.data(), digits.data() + digits.size(), count);
  if (result.ec != std::errc{}) {
    error = "cannot parse rev-list --count output";
    return false;
  }
  return true;
}

bool rev_list_all(std::string_view repo, const LineSplitter::LineSink& on_oid,
                  std::string& error) {
  std::vector<std::string> argv = base_argv(repo);
  argv.insert(argv.end(), {"rev-list", "--all", "--reverse"});
  return run_lines(argv, {}, on_oid, error);
}

bool log_stream(std::string_view repo, const ChunkSink& sink, std::string& error) {
  std::vector<std::string> argv = base_argv(repo);
  argv.insert(argv.end(), {"log", "--all", "--reverse", "--no-renames", "-U0"});
  append_safe_flags(argv);
  argv.emplace_back(kLogFormat);
  return run(argv, {}, sink, error);
}

bool verify_batch(std::string_view repo, std::string_view needle,
                  const std::vector<std::string>& candidates,
                  std::vector<std::string>& survivors, std::string& error) {
  survivors.clear();
  if (candidates.empty()) return true;

  std::string stdin_data;
  stdin_data.reserve(candidates.size() * 41);
  for (const std::string& sha : candidates) {
    stdin_data += sha;
    stdin_data += '\n';
  }

  std::vector<std::string> argv = base_argv(repo);
  argv.insert(argv.end(), {"log", "--stdin", "--no-walk", "--format=%H"});
  argv.emplace_back("-S");
  argv.emplace_back(needle);

  return run_lines(
      argv, stdin_data,
      [&](std::string_view line) {
        if (!line.empty()) survivors.emplace_back(line);
      },
      error);
}

}  // namespace pk::git
