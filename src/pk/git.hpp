#pragma once

#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

#include "pk/subprocess.hpp"

namespace pk::git {

// The log format the diff parser expects: a leading NUL marks a header line,
// then NUL-separated oid, parent list, author time, author name, and subject.
// The subject comes last because it is the only field that can contain spaces.
extern const char kLogFormat[];

// `git rev-list --all --count`, the number every index build is checked against.
bool rev_list_count(std::string_view repo, std::uint64_t& count, std::string& error);

// `git rev-list --all --reverse`: every commit, oldest first, so a commit's
// position in the stream is its ordinal (plan §2.4).
bool rev_list_all(std::string_view repo, const LineSplitter::LineSink& on_oid,
                  std::string& error);

// `git log --all --reverse --no-renames -U0` in the format above, streamed into
// `sink`. This is what an index build reads.
bool log_stream(std::string_view repo, const ChunkSink& sink, std::string& error);

// Feeds candidates to `git log --stdin --no-walk -S <needle>` and collects the
// survivors in git's own output order (plan §2.2, spikes.md S2).
//
// Deliberately passes no diff options. With `--no-renames` git reports a commit
// that merely moved the needle between files and plain `git log -S` does not,
// so the index is built one way and verified the other (spikes.md S4).
bool verify_batch(std::string_view repo, std::string_view needle,
                  const std::vector<std::string>& candidates,
                  std::vector<std::string>& survivors, std::string& error);

}  // namespace pk::git
