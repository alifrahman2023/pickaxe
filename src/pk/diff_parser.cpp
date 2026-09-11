#include "pk/diff_parser.hpp"

#include <charconv>

namespace pk {
namespace {

bool parse_u64(std::string_view text, std::uint64_t& out) {
  const char* end = text.data() + text.size();
  const auto result = std::from_chars(text.data(), end, out);
  return result.ec == std::errc{} && result.ptr == end;
}

bool parse_i64(std::string_view text, std::int64_t& out) {
  const char* end = text.data() + text.size();
  const auto result = std::from_chars(text.data(), end, out);
  return result.ec == std::errc{} && result.ptr == end;
}

// Splits on NUL, returning the field and advancing `rest`.
std::string_view next_field(std::string_view& rest) {
  const std::size_t sep = rest.find('\0');
  if (sep == std::string_view::npos) {
    const std::string_view all = rest;
    rest = {};
    return all;
  }
  const std::string_view field = rest.substr(0, sep);
  rest.remove_prefix(sep + 1);
  return field;
}

std::uint32_t count_tokens(std::string_view text) {
  std::uint32_t n = 0;
  std::size_t i = 0;
  while (i < text.size()) {
    while (i < text.size() && text[i] == ' ') ++i;
    if (i >= text.size()) break;
    ++n;
    while (i < text.size() && text[i] != ' ') ++i;
  }
  return n;
}

}  // namespace

std::int64_t hunk_body_lines(std::string_view header) {
  if (!header.starts_with("@@")) return -1;
  const std::size_t close = header.find("@@", 2);
  if (close == std::string_view::npos) return -1;

  std::string_view spans = header.substr(2, close - 2);
  std::int64_t total = 0;
  int ranges = 0;
  while (true) {
    const std::size_t start = spans.find_first_not_of(' ');
    if (start == std::string_view::npos) break;
    spans.remove_prefix(start);
    const std::size_t stop = spans.find(' ');
    std::string_view field = spans.substr(0, stop);
    if (field.size() < 2 || (field.front() != '-' && field.front() != '+')) return -1;
    field.remove_prefix(1);

    std::uint64_t count = 1;
    const std::size_t comma = field.find(',');
    if (comma != std::string_view::npos && !parse_u64(field.substr(comma + 1), count)) {
      return -1;
    }
    total += static_cast<std::int64_t>(count);
    ++ranges;
    if (stop == std::string_view::npos) break;
    spans.remove_prefix(stop);
  }
  return ranges == 2 ? total : -1;
}

DiffParser::DiffParser(HeaderFn on_header, LineFn on_line, SummaryFn on_summary)
    : on_header_(std::move(on_header)),
      on_line_(std::move(on_line)),
      on_summary_(std::move(on_summary)) {}

void DiffParser::feed(std::string_view chunk) {
  splitter_.feed(chunk, [this](std::string_view line) { handle_line(line); });
}

void DiffParser::finish() {
  splitter_.finish([this](std::string_view line) { handle_line(line); });
  if (in_commit_) end_commit();
}

void DiffParser::begin_commit(std::string_view fields) {
  if (in_commit_) end_commit();

  CommitHeader header;
  header.oid = next_field(fields);
  const std::string_view parents = next_field(fields);
  const std::string_view time = next_field(fields);
  header.author = next_field(fields);
  header.subject = fields;  // the subject is last and may contain anything

  header.parents = count_tokens(parents);
  if (!parse_i64(time, header.time)) header.time = 0;

  in_commit_ = true;
  summary_ = CommitSummary{};
  if (on_header_) on_header_(header);
}

void DiffParser::end_commit() {
  in_commit_ = false;
  ++commits_;
  if (on_summary_) on_summary_(summary_);
}

void DiffParser::handle_line(std::string_view line) {
  // A commit header is the only line that can start with NUL: a text file
  // containing one is binary to git, and binary filepairs emit no content.
  if (!line.empty() && line.front() == '\0') {
    if (pending_ > 0) {
      ++malformed_;
      pending_ = 0;
    }
    begin_commit(line.substr(1));
    return;
  }

  if (pending_ > 0) {
    if (!line.empty() && line.front() == '\\') {
      return;  // "\ No newline at end of file" is outside the line counts
    }
    --pending_;
    if (line.empty()) return;
    if (line.front() == '+') {
      ++summary_.added_lines;
      if (on_line_) on_line_(true, line.substr(1));
    } else if (line.front() == '-') {
      ++summary_.removed_lines;
      if (on_line_) on_line_(false, line.substr(1));
    }
    return;
  }

  if (line.starts_with("@@")) {
    const std::int64_t body = hunk_body_lines(line);
    if (body < 0) {
      ++malformed_;
    } else {
      pending_ = body;
    }
    return;
  }
  if (line.starts_with("diff --git")) {
    ++summary_.files;
    return;
  }
  if (line.starts_with("Binary files") || line.starts_with("GIT binary patch")) {
    summary_.binary = true;
  }
  // Everything else is metadata: index lines, mode lines, the ---/+++ pair,
  // and the blank line git puts between the header and the diff.
}

}  // namespace pk
