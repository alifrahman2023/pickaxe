#include "pk/subprocess.hpp"

#include <gtest/gtest.h>

#include <string>
#include <vector>

namespace {

std::vector<std::string> split_in_chunks(std::string_view text, std::size_t chunk) {
  pk::LineSplitter splitter;
  std::vector<std::string> lines;
  const auto sink = [&](std::string_view line) { lines.emplace_back(line); };
  for (std::size_t at = 0; at < text.size(); at += chunk) {
    splitter.feed(text.substr(at, chunk), sink);
  }
  splitter.finish(sink);
  return lines;
}

}  // namespace

TEST(LineSplitter, SplitsOnNewlinesAndDropsTheTerminator) {
  EXPECT_EQ(split_in_chunks("a\nbb\nccc\n", 64),
            (std::vector<std::string>{"a", "bb", "ccc"}));
}

TEST(LineSplitter, FlushesAnUnterminatedFinalLine) {
  EXPECT_EQ(split_in_chunks("a\nno newline here", 64),
            (std::vector<std::string>{"a", "no newline here"}));
  pk::LineSplitter splitter;
  std::vector<std::string> lines;
  splitter.feed("dangling", [&](std::string_view l) { lines.emplace_back(l); });
  EXPECT_TRUE(lines.empty()) << "a line is not emitted until it is complete";
}

TEST(LineSplitter, KeepsEmptyLines) {
  EXPECT_EQ(split_in_chunks("\n\na\n", 64),
            (std::vector<std::string>{"", "", "a"}));
}

TEST(LineSplitter, IsIndifferentToChunkBoundaries) {
  const std::string text = "first\n\nthird line\nfourth\n\n\nlast one without\n";
  const std::vector<std::string> expected = split_in_chunks(text, text.size());
  ASSERT_EQ(expected.size(), 7u);
  for (std::size_t chunk = 1; chunk <= text.size(); ++chunk) {
    EXPECT_EQ(split_in_chunks(text, chunk), expected)
        << "differs when fed " << chunk << " bytes at a time";
  }
}

TEST(LineSplitter, CarriesNulBytesThrough) {
  const std::string text = std::string("a\0b\nc\0", 6);
  const std::vector<std::string> lines = split_in_chunks(text, 1);
  ASSERT_EQ(lines.size(), 2u);
  EXPECT_EQ(lines[0], std::string("a\0b", 3));
  EXPECT_EQ(lines[1], std::string("c\0", 2));
}

TEST(LineSplitter, ResetDropsAPartialLine) {
  pk::LineSplitter splitter;
  std::vector<std::string> lines;
  const auto sink = [&](std::string_view l) { lines.emplace_back(l); };
  splitter.feed("partial", sink);
  splitter.reset();
  splitter.feed("whole\n", sink);
  splitter.finish(sink);
  EXPECT_EQ(lines, (std::vector<std::string>{"whole"}));
}
