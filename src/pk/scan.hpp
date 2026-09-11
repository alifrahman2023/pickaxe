#pragma once

#include <cstdint>
#include <cstdio>
#include <string>
#include <string_view>

namespace pk {

// What one pass of `git log -U0` over a repo's whole history contains. This is
// the phase-2 diagnostic: it proves the subprocess, git and parser layers see
// every commit and agree with git's own count, before anything is indexed.
struct ScanStats {
  std::uint64_t rev_list_count = 0;  // git rev-list --all --count
  std::uint64_t commits = 0;         // commits the log stream delivered
  std::uint64_t merges = 0;          // no diff body, so nothing to index (S1)
  std::uint64_t binary_commits = 0;  // unconditional candidates (S6)
  std::uint64_t empty_commits = 0;   // non-merge, nothing indexable
  std::uint64_t files = 0;
  std::uint64_t added_lines = 0;
  std::uint64_t removed_lines = 0;
  std::uint64_t changed_bytes = 0;
  std::uint64_t max_lines_in_commit = 0;
  std::uint64_t max_bytes_in_commit = 0;
  std::uint64_t malformed_hunks = 0;
  double seconds = 0.0;

  // The phase-2 exit criterion: the stream saw exactly the commits git counts.
  bool counts_agree() const { return commits == rev_list_count; }
};

// Streams the repo's history once and fills `out`. Returns false with `error`
// set if git could not be run.
bool scan(std::string_view repo, ScanStats& out, std::string& error);

void print_scan(const ScanStats& stats, std::FILE* to);

}  // namespace pk
