#pragma once

#include <cstdint>
#include <functional>
#include <string_view>

#include "pk/subprocess.hpp"

namespace pk {

// One commit's header, from the NUL-marked format in git.hpp. The views point
// into the parser's line buffer and are valid only for the callback.
struct CommitHeader {
  std::string_view oid;  // 40 hex characters
  std::string_view author;
  std::string_view subject;
  std::int64_t time = 0;     // author time, seconds since the epoch
  std::uint32_t parents = 0;  // >1 is a merge, which has no diff body (S1)
};

// What a commit's diff amounted to, delivered once the diff is complete.
struct CommitSummary {
  std::uint32_t files = 0;
  std::uint32_t added_lines = 0;
  std::uint32_t removed_lines = 0;
  // The diff said `Binary files ... differ`: content changed that the pickaxe
  // searches and this stream never showed us, so the commit has to be an
  // unconditional candidate (spikes.md S6).
  bool binary = false;
};

// Streaming parser for `git log -U0`. Push bytes in, take callbacks out. It
// holds at most one line at a time, so memory is flat across a 100k-commit
// stream.
//
// Hunk bodies are consumed by the line count in the `@@` header rather than by
// looking for lines that start with `+` or `-`. That is not fussiness: a
// removed line whose text begins with `-- ` renders as `--- ...` and is
// otherwise indistinguishable from a file header.
class DiffParser {
 public:
  using HeaderFn = std::function<void(const CommitHeader&)>;
  using LineFn = std::function<void(bool added, std::string_view text)>;
  using SummaryFn = std::function<void(const CommitSummary&)>;

  DiffParser(HeaderFn on_header, LineFn on_line, SummaryFn on_summary);

  void feed(std::string_view chunk);
  void finish();  // flushes the last commit; call once at EOF

  std::uint64_t commits() const { return commits_; }
  std::uint64_t malformed_hunks() const { return malformed_; }

 private:
  void handle_line(std::string_view line);
  void begin_commit(std::string_view fields);
  void end_commit();

  HeaderFn on_header_;
  LineFn on_line_;
  SummaryFn on_summary_;

  LineSplitter splitter_;
  CommitSummary summary_;
  std::int64_t pending_ = 0;  // unconsumed hunk-body lines
  std::uint64_t commits_ = 0;
  std::uint64_t malformed_ = 0;
  bool in_commit_ = false;
};

// Body-line count promised by a `-U0` hunk header, or -1 if it does not parse.
// Exposed for testing.
std::int64_t hunk_body_lines(std::string_view header);

}  // namespace pk
