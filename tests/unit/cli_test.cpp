#include "pk/cli.hpp"

#include <gtest/gtest.h>

#include <initializer_list>
#include <string>
#include <vector>

#include "pk/version.hpp"

namespace {

pk::Options Parse(std::initializer_list<const char*> args) {
  std::vector<const char*> argv{"pk"};
  argv.insert(argv.end(), args);
  return pk::parse_args(static_cast<int>(argv.size()), argv.data());
}

}  // namespace

TEST(Cli, QueryIsTheDefaultForm) {
  const pk::Options o = Parse({"-S", "ZLIB_BUF_MAX"});
  EXPECT_TRUE(o.error.empty()) << o.error;
  EXPECT_EQ(o.command, pk::Command::Query);
  EXPECT_EQ(o.needle, "ZLIB_BUF_MAX");
  EXPECT_EQ(o.repo, ".");
  EXPECT_FALSE(o.verify);
}

TEST(Cli, AcceptsAttachedNeedleLikeGit) {
  const pk::Options o = Parse({"-SZLIB_BUF_MAX"});
  EXPECT_TRUE(o.error.empty()) << o.error;
  EXPECT_EQ(o.needle, "ZLIB_BUF_MAX");
}

TEST(Cli, VerifyAndRepoPath) {
  const pk::Options o = Parse({"-C", "/tmp/git", "-S", "needle", "--verify"});
  EXPECT_TRUE(o.error.empty()) << o.error;
  EXPECT_EQ(o.repo, "/tmp/git");
  EXPECT_TRUE(o.verify);
}

TEST(Cli, NeedleMayContainSpacesAndDashes) {
  const pk::Options o = Parse({"-S", "--not-a-flag here"});
  EXPECT_TRUE(o.error.empty()) << o.error;
  EXPECT_EQ(o.needle, "--not-a-flag here");
}

TEST(Cli, Subcommands) {
  EXPECT_EQ(Parse({"index"}).command, pk::Command::Index);
  EXPECT_EQ(Parse({"update"}).command, pk::Command::Update);
  EXPECT_EQ(Parse({"compact"}).command, pk::Command::Compact);
  EXPECT_EQ(Parse({"stats"}).command, pk::Command::Stats);
  EXPECT_EQ(Parse({"scan"}).command, pk::Command::Scan);
}

TEST(Cli, SubcommandTakesAPositionalPath) {
  const pk::Options o = Parse({"index", "/src/git"});
  EXPECT_TRUE(o.error.empty()) << o.error;
  EXPECT_EQ(o.command, pk::Command::Index);
  EXPECT_EQ(o.repo, "/src/git");
}

TEST(Cli, HelpAndVersionWinOverEverythingElse) {
  EXPECT_EQ(Parse({"--help"}).command, pk::Command::Help);
  EXPECT_EQ(Parse({"-h"}).command, pk::Command::Help);
  EXPECT_EQ(Parse({"index", "--help"}).command, pk::Command::Help);
  EXPECT_EQ(Parse({"--version"}).command, pk::Command::Version);
  EXPECT_EQ(Parse({"-V"}).command, pk::Command::Version);
}

TEST(Cli, RejectsBadInvocations) {
  EXPECT_FALSE(Parse({}).error.empty());                   // bare `pk`
  EXPECT_FALSE(Parse({"-S"}).error.empty());               // missing argument
  EXPECT_FALSE(Parse({"-C"}).error.empty());               // missing argument
  EXPECT_FALSE(Parse({"--nope"}).error.empty());           // unknown option
  EXPECT_FALSE(Parse({"frobnicate"}).error.empty());       // unknown command
  EXPECT_FALSE(Parse({"index", "-S", "x"}).error.empty()); // -S is query-only
  EXPECT_FALSE(Parse({"--verify"}).error.empty());         // query without a needle
}

TEST(Cli, RejectsFlagsThatArePlanNonGoals) {
  for (const char* flag : {"-i", "--regexp-ignore-case", "-G", "--pickaxe-regex"}) {
    const pk::Options o = Parse({flag, "-S", "x"});
    EXPECT_FALSE(o.error.empty()) << flag << " should be rejected";
  }
}

TEST(Version, IsNotEmpty) { EXPECT_FALSE(pk::version().empty()); }
