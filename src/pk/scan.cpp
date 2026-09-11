#include "pk/scan.hpp"

#include <chrono>

#include "pk/diff_parser.hpp"
#include "pk/git.hpp"

namespace pk {
namespace {

void print_count(std::FILE* to, const char* label, std::uint64_t value,
                 std::uint64_t of = 0) {
  if (of == 0) {
    std::fprintf(to, "  %-22s %14llu\n", label,
                 static_cast<unsigned long long>(value));
    return;
  }
  std::fprintf(to, "  %-22s %14llu  %5.2f%%\n", label,
               static_cast<unsigned long long>(value),
               100.0 * static_cast<double>(value) / static_cast<double>(of));
}

}  // namespace

bool scan(std::string_view repo, ScanStats& out, std::string& error) {
  out = ScanStats{};
  const auto started = std::chrono::steady_clock::now();

  if (!git::rev_list_count(repo, out.rev_list_count, error)) return false;

  std::uint32_t parents = 0;
  std::uint64_t commit_bytes = 0;

  DiffParser parser(
      [&](const CommitHeader& header) {
        parents = header.parents;
        commit_bytes = 0;
      },
      [&](bool, std::string_view text) { commit_bytes += text.size(); },
      [&](const CommitSummary& summary) {
        const std::uint64_t lines = summary.added_lines + summary.removed_lines;
        out.files += summary.files;
        out.added_lines += summary.added_lines;
        out.removed_lines += summary.removed_lines;
        out.changed_bytes += commit_bytes;
        if (lines > out.max_lines_in_commit) out.max_lines_in_commit = lines;
        if (commit_bytes > out.max_bytes_in_commit) {
          out.max_bytes_in_commit = commit_bytes;
        }
        if (summary.binary) ++out.binary_commits;
        if (parents > 1) {
          ++out.merges;
        } else if (lines == 0) {
          ++out.empty_commits;
        }
      });

  if (!git::log_stream(repo, [&](std::string_view chunk) { parser.feed(chunk); },
                       error)) {
    return false;
  }
  parser.finish();

  out.commits = parser.commits();
  out.malformed_hunks = parser.malformed_hunks();
  out.seconds = std::chrono::duration<double>(
                    std::chrono::steady_clock::now() - started)
                    .count();
  return true;
}

void print_scan(const ScanStats& stats, std::FILE* to) {
  const std::uint64_t non_merge = stats.commits - stats.merges;

  std::fprintf(to, "commits\n");
  print_count(to, "git rev-list --count", stats.rev_list_count);
  print_count(to, "seen in the log", stats.commits);
  print_count(to, "merges", stats.merges, stats.commits);
  print_count(to, "non-merge", non_merge, stats.commits);
  if (non_merge > 0) {
    print_count(to, "nothing indexable", stats.empty_commits, non_merge);
    print_count(to, "touch a binary file", stats.binary_commits, non_merge);
  }

  std::fprintf(to, "changed content\n");
  print_count(to, "filepairs", stats.files);
  print_count(to, "lines added", stats.added_lines);
  print_count(to, "lines removed", stats.removed_lines);
  print_count(to, "bytes", stats.changed_bytes);
  print_count(to, "widest commit, lines", stats.max_lines_in_commit);
  print_count(to, "widest commit, bytes", stats.max_bytes_in_commit);
  print_count(to, "malformed hunks", stats.malformed_hunks);

  std::fprintf(to, "throughput\n");
  std::fprintf(to, "  %-22s %14.2f s\n", "elapsed", stats.seconds);
  if (stats.seconds > 0) {
    std::fprintf(to, "  %-22s %14.0f commits/s\n", "rate",
                 static_cast<double>(stats.commits) / stats.seconds);
    std::fprintf(to, "  %-22s %14.1f MB/s\n", "changed content",
                 static_cast<double>(stats.changed_bytes) / stats.seconds / 1e6);
  }

  std::fprintf(to, "\n%s\n",
               stats.counts_agree()
                   ? "counts agree: the stream saw every commit git counts"
                   : "MISMATCH: the log stream and rev-list disagree");
}

}  // namespace pk
