#include <gtest/gtest.h>
#include <unistd.h>

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <vector>

#include "pk/diff_parser.hpp"
#include "pk/git.hpp"
#include "pk/scan.hpp"
#include "pk/subprocess.hpp"

namespace {

std::filesystem::path g_fixtures;

// Builds the synthetic repos once for the whole binary. They are cheap to make
// and expensive to make per test.
class Fixtures : public ::testing::Environment {
 public:
  void SetUp() override {
    g_fixtures = std::filesystem::temp_directory_path() /
                 ("pk-git-stream-" + std::to_string(::getpid()));
    const std::string cmd =
        std::string(PK_FIXTURE_SCRIPT) + " '" + g_fixtures.string() + "' >/dev/null";
    ASSERT_EQ(std::system(cmd.c_str()), 0) << "make_repo.sh failed";
  }

  void TearDown() override {
    std::error_code ignored;
    std::filesystem::remove_all(g_fixtures, ignored);
  }
};

[[maybe_unused]] const ::testing::Environment* kFixtures =
    ::testing::AddGlobalTestEnvironment(new Fixtures);

std::string repo(std::string_view name) {
  return (g_fixtures / name).string();
}

// Runs a command through the shell and returns its stdout. Used only to get an
// independent answer to compare pk's against.
std::string shell(const std::string& command) {
  std::string out;
  FILE* pipe = ::popen(command.c_str(), "r");
  if (pipe == nullptr) return out;
  char buf[4096];
  std::size_t got = 0;
  while ((got = std::fread(buf, 1, sizeof buf, pipe)) > 0) out.append(buf, got);
  ::pclose(pipe);
  return out;
}

std::vector<std::string> lines_of(const std::string& text) {
  std::vector<std::string> lines;
  pk::LineSplitter splitter;
  const auto sink = [&](std::string_view line) {
    if (!line.empty()) lines.emplace_back(line);
  };
  splitter.feed(text, sink);
  splitter.finish(sink);
  return lines;
}

std::vector<std::string> all_oids(const std::string& path) {
  std::vector<std::string> oids;
  std::string error;
  EXPECT_TRUE(pk::git::rev_list_all(
      path, [&](std::string_view oid) { oids.emplace_back(oid); }, error))
      << error;
  return oids;
}

}  // namespace

TEST(Git, RevListCountAgreesWithRevListAll) {
  for (const char* name : {"pickaxe", "evil-merge", "ties", "rename"}) {
    std::uint64_t count = 0;
    std::string error;
    ASSERT_TRUE(pk::git::rev_list_count(repo(name), count, error)) << error;
    EXPECT_EQ(count, all_oids(repo(name)).size()) << name;
  }
}

TEST(Git, RevListAllIsOldestFirstSoPositionIsTheOrdinal) {
  const std::vector<std::string> oids = all_oids(repo("pickaxe"));
  ASSERT_FALSE(oids.empty());
  const std::string newest =
      lines_of(shell("git -C '" + repo("pickaxe") + "' rev-list --all | head -1")).front();
  EXPECT_NE(oids.front(), newest) << "ordinal 0 must be the oldest commit";
  EXPECT_EQ(oids.back(), newest);
}

// The phase-2 exit criterion.
TEST(Scan, SeesEveryCommitGitCounts) {
  for (const char* name : {"pickaxe", "evil-merge", "ties", "rename"}) {
    pk::ScanStats stats;
    std::string error;
    ASSERT_TRUE(pk::scan(repo(name), stats, error)) << error;
    EXPECT_EQ(stats.commits, stats.rev_list_count) << name;
    EXPECT_TRUE(stats.counts_agree()) << name;
    EXPECT_EQ(stats.malformed_hunks, 0u) << name;
  }
}

TEST(Scan, CountsTheMergeAndGivesItNoContent) {
  pk::ScanStats stats;
  std::string error;
  ASSERT_TRUE(pk::scan(repo("evil-merge"), stats, error)) << error;
  EXPECT_EQ(stats.commits, 4u);
  EXPECT_EQ(stats.merges, 1u);
  // base, main edit, side edit each rewrite the single line of f.txt.
  EXPECT_EQ(stats.added_lines, 3u);
  EXPECT_EQ(stats.removed_lines, 2u);
}

TEST(Scan, FlagsTheCommitThatTouchesABinaryFile) {
  pk::ScanStats stats;
  std::string error;
  ASSERT_TRUE(pk::scan(repo("pickaxe"), stats, error)) << error;
  EXPECT_EQ(stats.binary_commits, 1u) << "spikes.md S6: this one must be a candidate";
  // The mode-only commit changes no content at all.
  EXPECT_GE(stats.empty_commits, 1u);
}

TEST(Scan, SeesARenameAsADeleteAndAnAddUnderNoRenames) {
  pk::ScanStats stats;
  std::string error;
  ASSERT_TRUE(pk::scan(repo("rename"), stats, error)) << error;
  EXPECT_EQ(stats.commits, 2u);
  EXPECT_EQ(stats.files, 3u) << "one add, then a delete plus an add";
  EXPECT_EQ(stats.added_lines, 12u);
  EXPECT_EQ(stats.removed_lines, 6u);
}

TEST(Git, VerifyBatchReproducesPlainGitLogDashS) {
  const std::string path = repo("pickaxe");
  const std::vector<std::string> expected = lines_of(
      shell("git -C '" + path + "' log --all --no-color -S ZLIB_BUF_MAX --format=%H"));
  ASSERT_EQ(expected.size(), 3u);

  // Descending ordinal is rev-list order, which is what makes git's output
  // order right (plan §2.4, spikes.md S3).
  std::vector<std::string> candidates = all_oids(path);
  std::reverse(candidates.begin(), candidates.end());

  std::vector<std::string> survivors;
  std::string error;
  ASSERT_TRUE(pk::git::verify_batch(path, "ZLIB_BUF_MAX", candidates, survivors, error))
      << error;
  EXPECT_EQ(survivors, expected);
}

TEST(Git, VerifyBatchFindsANeedleIntroducedByARootCommit) {
  const std::string path = repo("pickaxe");
  std::vector<std::string> survivors;
  std::string error;
  ASSERT_TRUE(
      pk::git::verify_batch(path, "ROOT_ONLY_NEEDLE", all_oids(path), survivors, error))
      << error;
  EXPECT_EQ(survivors, lines_of(shell("git -C '" + path +
                                      "' log --all --no-color -S ROOT_ONLY_NEEDLE "
                                      "--format=%H")));
}

TEST(Git, VerifyBatchReturnsNothingForANeedleThatIsNowhere) {
  const std::string path = repo("pickaxe");
  std::vector<std::string> survivors;
  std::string error;
  ASSERT_TRUE(pk::git::verify_batch(path, "NEEDLE_THAT_IS_NOWHERE", all_oids(path),
                                    survivors, error))
      << error;
  EXPECT_TRUE(survivors.empty());
}

TEST(Git, VerifyBatchWithNoCandidatesRunsNothing) {
  std::vector<std::string> survivors{"stale"};
  std::string error;
  EXPECT_TRUE(pk::git::verify_batch(repo("pickaxe"), "anything", {}, survivors, error));
  EXPECT_TRUE(survivors.empty());
}

// The deadlock the notes warn about: a stdin payload larger than a pipe buffer
// while the child is also producing stdout. Without poll() on both directions
// this hangs forever rather than failing.
TEST(Git, VerifyBatchSurvivesAStdinPayloadBiggerThanAPipeBuffer) {
  const std::string path = repo("pickaxe");
  const std::vector<std::string> truth = lines_of(
      shell("git -C '" + path + "' log --all --no-color -S ZLIB_BUF_MAX --format=%H"));
  ASSERT_FALSE(truth.empty());

  std::vector<std::string> candidates;
  candidates.reserve(8000);
  for (int i = 0; i < 8000; ++i) candidates.push_back(truth.front());
  ASSERT_GT(candidates.size() * 41, 1u << 16) << "must exceed a 64 KB pipe buffer";

  std::vector<std::string> survivors;
  std::string error;
  ASSERT_TRUE(pk::git::verify_batch(path, "ZLIB_BUF_MAX", candidates, survivors, error))
      << error;
  ASSERT_FALSE(survivors.empty());
  for (const std::string& sha : survivors) EXPECT_EQ(sha, truth.front());
}

TEST(Git, ReportsAnErrorForSomethingThatIsNotARepository) {
  std::uint64_t count = 0;
  std::string error;
  EXPECT_FALSE(pk::git::rev_list_count("/", count, error));
  EXPECT_FALSE(error.empty());
}

TEST(Subprocess, ReportsACommandThatDoesNotExist) {
  pk::Subprocess child;
  const bool started = child.start({"pk-definitely-not-on-path-42"});
  if (started) {
    // Some platforms report the failure through the child's exit status
    // instead of through posix_spawnp.
    std::string ignored;
    child.read_all([](std::string_view) {});
    EXPECT_EQ(child.wait(), 127);
  } else {
    EXPECT_FALSE(child.error().empty());
  }
}

TEST(Subprocess, StreamsMoreThanOneBufferOfOutput) {
  pk::Subprocess child;
  ASSERT_TRUE(child.start({"git", "-C", repo("pickaxe"), "log", "--all", "-p",
                           "--format=%H", "--no-color"}))
      << child.error();
  std::size_t bytes = 0;
  int chunks = 0;
  ASSERT_TRUE(child.read_all([&](std::string_view chunk) {
    bytes += chunk.size();
    ++chunks;
  })) << child.error();
  EXPECT_EQ(child.wait(), 0);
  EXPECT_GT(bytes, 0u);
  EXPECT_GE(chunks, 1);
}
