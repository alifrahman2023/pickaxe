#include "pk/cli.hpp"

#include <cstddef>
#include <vector>

namespace pk {
namespace {

constexpr std::string_view kUsage =
    "pk — trigram-indexed `git log -S`\n"
    "\n"
    "usage:\n"
    "  pk [-C <path>] -S <needle> [--verify]   search history for <needle>\n"
    "  pk index   [path]                       build the index\n"
    "  pk update  [path]                       append newly reachable commits\n"
    "  pk compact [path]                       merge index segments\n"
    "  pk stats   [path]                       index size and trigram histogram\n"
    "\n"
    "options:\n"
    "  -S <needle>   the string to search for (>= 3 bytes, no newline)\n"
    "  -C <path>     run as if started in <path>\n"
    "  --verify      also run `git log --all -S` and diff the two outputs\n"
    "  -h, --help    this text\n"
    "  -V, --version version string\n"
    "\n"
    "Not supported in v1: -i, -G, --pickaxe-regex. Merge commits are not reported,\n"
    "matching `git log -S`'s own behaviour.\n";

// Flags git's pickaxe accepts that pk deliberately does not implement (plan §10).
bool unsupported_flag(std::string_view a) {
  return a == "-i" || a == "--regexp-ignore-case" || a == "-G" || a == "--pickaxe-regex";
}

Command subcommand_for(std::string_view a) {
  if (a == "index") return Command::Index;
  if (a == "update") return Command::Update;
  if (a == "compact") return Command::Compact;
  if (a == "stats") return Command::Stats;
  if (a == "scan") return Command::Scan;
  return Command::Query;
}

}  // namespace

std::string_view usage() { return kUsage; }

Options parse_args(int argc, const char* const* argv) {
  Options opt;
  std::vector<std::string_view> args;
  for (int i = 1; i < argc; ++i) args.emplace_back(argv[i]);

  if (args.empty()) {
    opt.command = Command::Help;
    opt.error = "no command or needle given";
    return opt;
  }

  std::size_t i = 0;
  bool is_subcmd = false;
  if (!args[0].empty() && args[0].front() != '-') {
    opt.command = subcommand_for(args[0]);
    if (opt.command == Command::Query) {
      opt.error = "unknown command '" + std::string(args[0]) + "'";
      return opt;
    }
    is_subcmd = true;
    i = 1;
  }

  bool needle_seen = false;
  bool path_seen = false;

  for (; i < args.size(); ++i) {
    std::string_view a = args[i];

    if (a == "-h" || a == "--help") {
      opt.command = Command::Help;
      return opt;
    }
    if (a == "-V" || a == "--version") {
      opt.command = Command::Version;
      return opt;
    }
    if (a == "--verify") {
      opt.verify = true;
      continue;
    }
    if (unsupported_flag(a)) {
      opt.error = std::string(a) + " is not supported in v1";
      return opt;
    }
    if (a == "-S" || a == "-C") {
      if (i + 1 >= args.size()) {
        opt.error = std::string(a) + " needs an argument";
        return opt;
      }
      std::string_view value = args[++i];
      if (a == "-S") {
        opt.needle.assign(value);
        needle_seen = true;
      } else {
        opt.repo.assign(value);
        path_seen = true;
      }
      continue;
    }
    if (a.size() > 2 && a.substr(0, 2) == "-S") {  // git also accepts -S<needle>
      opt.needle.assign(a.substr(2));
      needle_seen = true;
      continue;
    }
    if (!a.empty() && a.front() == '-') {
      opt.error = "unknown option '" + std::string(a) + "'";
      return opt;
    }
    if (is_subcmd && !path_seen) {  // `pk index <path>`
      opt.repo.assign(a);
      path_seen = true;
      continue;
    }
    opt.error = "unexpected argument '" + std::string(a) + "'";
    return opt;
  }

  if (is_subcmd) {
    if (needle_seen) opt.error = "-S is only valid for a query, not a subcommand";
    return opt;
  }
  if (!needle_seen) opt.error = "a query needs -S <needle>";
  return opt;
}

}  // namespace pk
