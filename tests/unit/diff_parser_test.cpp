#include "pk/diff_parser.hpp"

#include <gtest/gtest.h>

#include <algorithm>
#include <string>
#include <vector>

namespace {

// A backtick stands in for NUL, which cannot be written inside a raw literal.
// It appears nowhere else in the fixture.
std::string with_nuls(std::string_view text) {
  std::string out(text);
  for (char& c : out) {
    if (c == '`') c = '\0';
  }
  return out;
}

// Shaped exactly like `git log -U0` output under git.hpp's format, verified
// against the fixture repos: a root commit, removed lines whose text begins
// with `--` and `++` (the case counted parsing exists for), a binary filepair,
// a mode-only change, a two-hunk commit with no trailing newline, and a merge
// with no diff body at all.
constexpr std::string_view kStream =
    R"STREAM(`aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111``1700000060`pk fixture`root commit

diff --git a/a.txt b/a.txt
new file mode 100644
index 0000000..1111111
--- /dev/null
+++ b/a.txt
@@ -0,0 +1,2 @@
+first line
+second line
`bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222`aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111`1700000120`pk fixture`removes lines that look like headers

diff --git a/a.txt b/a.txt
index 1111111..2222222 100644
--- a/a.txt
+++ b/a.txt
@@ -1,2 +1 @@
--- dashes are content here
-++ so are plusses
+replacement
`cccc3333cccc3333cccc3333cccc3333cccc3333`bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222`1700000180`pk fixture`adds a binary file

diff --git a/blob.bin b/blob.bin
new file mode 100644
index 0000000..3333333
Binary files /dev/null and b/blob.bin differ
`dddd4444dddd4444dddd4444dddd4444dddd4444`cccc3333cccc3333cccc3333cccc3333cccc3333`1700000240`pk fixture`mode-only change

diff --git a/a.txt b/a.txt
old mode 100644
new mode 100755
`eeee5555eeee5555eeee5555eeee5555eeee5555`dddd4444dddd4444dddd4444dddd4444dddd4444`1700000300`pk fixture`two hunks, no trailing newline

diff --git a/a.txt b/a.txt
index 2222222..4444444 100644
--- a/a.txt
+++ b/a.txt
@@ -1 +1 @@
-replacement
+replaced again
@@ -5,0 +6 @@
+appended without a newline
\ No newline at end of file
`ffff6666ffff6666ffff6666ffff6666ffff6666`eeee5555eeee5555eeee5555eeee5555eeee5555 dddd4444dddd4444dddd4444dddd4444dddd4444`1700000360`pk fixture`merge, no diff body

)STREAM";

struct Parsed {
  std::vector<std::string> events;
  std::uint64_t commits = 0;
  std::uint64_t malformed = 0;
};

Parsed parse_in_chunks(std::string_view stream, std::size_t chunk) {
  Parsed result;
  pk::DiffParser parser(
      [&](const pk::CommitHeader& h) {
        result.events.push_back("commit " + std::string(h.oid.substr(0, 4)) +
                                " parents=" + std::to_string(h.parents) +
                                " at=" + std::to_string(h.time) +
                                " author=" + std::string(h.author) +
                                " subject=" + std::string(h.subject));
      },
      [&](bool added, std::string_view text) {
        result.events.push_back((added ? "add " : "del ") + std::string(text));
      },
      [&](const pk::CommitSummary& s) {
        result.events.push_back("end files=" + std::to_string(s.files) + " +" +
                                std::to_string(s.added_lines) + " -" +
                                std::to_string(s.removed_lines) +
                                (s.binary ? " binary" : ""));
      });
  for (std::size_t at = 0; at < stream.size(); at += chunk) {
    parser.feed(stream.substr(at, chunk));
  }
  parser.finish();
  result.commits = parser.commits();
  result.malformed = parser.malformed_hunks();
  return result;
}

bool has_event(const Parsed& p, const std::string& event) {
  return std::find(p.events.begin(), p.events.end(), event) != p.events.end();
}

const Parsed& parsed() {
  static const Parsed p = parse_in_chunks(with_nuls(kStream), 1 << 20);
  return p;
}

}  // namespace

TEST(HunkHeader, CountsBodyLinesFromTheRanges) {
  EXPECT_EQ(pk::hunk_body_lines("@@ -0,0 +1,2 @@"), 2);
  EXPECT_EQ(pk::hunk_body_lines("@@ -1,2 +1 @@"), 3);
  EXPECT_EQ(pk::hunk_body_lines("@@ -1 +1 @@"), 2);
  EXPECT_EQ(pk::hunk_body_lines("@@ -5,0 +6 @@"), 1);
  EXPECT_EQ(pk::hunk_body_lines("@@ -1,0 +1,0 @@"), 0);
}

TEST(HunkHeader, IgnoresTheTrailingFunctionContext) {
  EXPECT_EQ(pk::hunk_body_lines("@@ -4 +4 @@ RENAMED_NEEDLE lives here"), 2);
  EXPECT_EQ(pk::hunk_body_lines("@@ -4 +4 @@ static int f(void) @@ x"), 2);
}

TEST(HunkHeader, RejectsWhatIsNotAHunkHeader) {
  EXPECT_EQ(pk::hunk_body_lines("@@ nonsense @@"), -1);
  EXPECT_EQ(pk::hunk_body_lines("@@ -1,2 @@"), -1);  // one range, not two
  EXPECT_EQ(pk::hunk_body_lines("@@ -1,x +1 @@"), -1);
  EXPECT_EQ(pk::hunk_body_lines("diff --git a/x b/x"), -1);
  EXPECT_EQ(pk::hunk_body_lines("@@ -1 +1"), -1);  // unterminated
}

TEST(DiffParser, ParsesEveryCommitInTheStream) {
  EXPECT_EQ(parsed().commits, 6u);
  EXPECT_EQ(parsed().malformed, 0u);
}

TEST(DiffParser, ReadsHeaderFields) {
  ASSERT_FALSE(parsed().events.empty());
  EXPECT_EQ(parsed().events.front(),
            "commit aaaa parents=0 at=1700000060 author=pk fixture "
            "subject=root commit");
}

TEST(DiffParser, CountedHunksSurviveContentThatLooksLikeAHeader) {
  EXPECT_TRUE(has_event(parsed(), "del -- dashes are content here"));
  EXPECT_TRUE(has_event(parsed(), "del ++ so are plusses"));
  EXPECT_TRUE(has_event(parsed(), "add replacement"));
  EXPECT_TRUE(has_event(parsed(), "end files=1 +1 -2"));
}

TEST(DiffParser, TheFileHeaderPairIsNeverMistakenForContent) {
  EXPECT_FALSE(has_event(parsed(), "del  /dev/null"));
  EXPECT_FALSE(has_event(parsed(), "add + b/a.txt"));
  EXPECT_FALSE(has_event(parsed(), "del -- a/a.txt"));
}

TEST(DiffParser, BinaryFilepairIsFlaggedAndYieldsNoLines) {
  EXPECT_TRUE(has_event(parsed(), "end files=1 +0 -0 binary"));
  // Only that one commit; "binary" also appears in a subject line, so match
  // the summary events alone.
  EXPECT_EQ(std::count_if(parsed().events.begin(), parsed().events.end(),
                          [](const std::string& e) {
                            return e.starts_with("end") &&
                                   e.find("binary") != std::string::npos;
                          }),
            1);
}

TEST(DiffParser, ModeOnlyChangeIsOneFilepairWithNoContent) {
  EXPECT_EQ(std::count(parsed().events.begin(), parsed().events.end(),
                       "end files=1 +0 -0"),
            1);
}

TEST(DiffParser, MergeIsReportedWithItsParentCountAndNoBody) {
  ASSERT_GE(parsed().events.size(), 2u);
  EXPECT_EQ(parsed().events[parsed().events.size() - 2],
            "commit ffff parents=2 at=1700000360 author=pk fixture "
            "subject=merge, no diff body");
  EXPECT_EQ(parsed().events.back(), "end files=0 +0 -0");
}

TEST(DiffParser, NoNewlineMarkerIsNotCountedAsABodyLine) {
  EXPECT_TRUE(has_event(parsed(), "add appended without a newline"));
  EXPECT_TRUE(has_event(parsed(), "add replaced again"));
  EXPECT_EQ(std::count_if(parsed().events.begin(), parsed().events.end(),
                          [](const std::string& e) {
                            return e.find('\\') != std::string::npos;
                          }),
            0);
}

TEST(DiffParser, IsIndifferentToChunkBoundaries) {
  const std::string stream = with_nuls(kStream);
  for (std::size_t chunk : {std::size_t{1}, std::size_t{2}, std::size_t{3},
                            std::size_t{7}, std::size_t{13}, std::size_t{64},
                            std::size_t{511}, std::size_t{4096}}) {
    const Parsed part = parse_in_chunks(stream, chunk);
    EXPECT_EQ(part.events, parsed().events) << "differs at chunk size " << chunk;
    EXPECT_EQ(part.commits, parsed().commits);
  }
}

TEST(DiffParser, HandlesAnEmptyStream) {
  const Parsed p = parse_in_chunks("", 16);
  EXPECT_EQ(p.commits, 0u);
  EXPECT_TRUE(p.events.empty());
}
