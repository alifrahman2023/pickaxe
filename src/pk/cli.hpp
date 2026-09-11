#pragma once

#include <string>
#include <string_view>

namespace pk {

enum class Command {
  Query,    // pk [-C <path>] -S <needle> [--verify]   — the default form
  Index,    // pk index [path]
  Update,   // pk update [path]
  Compact,  // pk compact [path]
  Stats,    // pk stats [path]
  Scan,     // pk scan [path]  — hidden, diff-parser diagnostics (phase 2)
  Help,
  Version,
};

struct Options {
  Command command = Command::Query;
  std::string needle;   // Query only
  std::string repo = ".";
  bool verify = false;  // --verify: also run git log -S and diff the two outputs
  std::string error;    // non-empty => the invocation was rejected; holds the reason
};

// Parses argv[1..argc). Never throws and never exits: a bad invocation comes back
// with `error` set so the caller decides how to report it. Lives in the library
// rather than main.cpp so it can be tested directly.
Options parse_args(int argc, const char* const* argv);

// Usage text, printed for --help and alongside any parse error.
std::string_view usage();

}  // namespace pk
