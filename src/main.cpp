// Thin entry point: parse argv, dispatch, map the result to an exit code.
// All real logic lives in libpk so the tests can reach it (context/notes.md §3).

#include <cstdio>
#include <string_view>

#include "pk/cli.hpp"
#include "pk/scan.hpp"
#include "pk/version.hpp"

namespace {

constexpr int kOk = 0;
constexpr int kFailed = 1;
constexpr int kUsageError = 2;

int run_scan(const pk::Options& opt) {
  pk::ScanStats stats;
  std::string error;
  if (!pk::scan(opt.repo, stats, error)) {
    std::fprintf(stderr, "pk: %s\n", error.c_str());
    return kFailed;
  }
  pk::print_scan(stats, stdout);
  return stats.counts_agree() ? kOk : kFailed;
}

int not_implemented(std::string_view what, int phase) {
  std::fprintf(stderr, "pk: %.*s is not implemented yet (plan phase %d)\n",
               static_cast<int>(what.size()), what.data(), phase);
  return kFailed;
}

}  // namespace

int main(int argc, char** argv) {
  const pk::Options opt = pk::parse_args(argc, argv);

  if (!opt.error.empty()) {
    std::fprintf(stderr, "pk: %s\n\n%s", opt.error.c_str(), pk::usage().data());
    return kUsageError;
  }

  switch (opt.command) {
    case pk::Command::Help:
      std::fputs(pk::usage().data(), stdout);
      return kOk;
    case pk::Command::Version:
      std::fprintf(stdout, "pk %.*s\n", static_cast<int>(pk::version().size()),
                   pk::version().data());
      return kOk;
    case pk::Command::Scan:
      return run_scan(opt);
    case pk::Command::Stats:
      return not_implemented("stats", 3);
    case pk::Command::Index:
      return not_implemented("index", 4);
    case pk::Command::Query:
      return not_implemented("-S query", 5);
    case pk::Command::Update:
      return not_implemented("update", 7);
    case pk::Command::Compact:
      return not_implemented("compact", 7);
  }
  return kFailed;
}
