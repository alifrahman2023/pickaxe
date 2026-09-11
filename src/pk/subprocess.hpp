#pragma once

#include <sys/types.h>

#include <functional>
#include <string>
#include <string_view>
#include <vector>

namespace pk {

// Fed successive chunks of a child's stdout. The view is valid only for the
// duration of the call: it points into a buffer the next read overwrites
// (context/notes.md §8).
using ChunkSink = std::function<void(std::string_view)>;

// One child process with its stdout on a pipe, and optionally its stdin too.
// Owns both descriptors and the child; the destructor closes and reaps, so an
// early return cannot leak a zombie (notes §8, §10).
//
// stderr is deliberately inherited, so git's own diagnostics reach the user
// instead of vanishing into a pipe nobody drains.
class Subprocess {
 public:
  Subprocess() = default;
  ~Subprocess();

  Subprocess(const Subprocess&) = delete;
  Subprocess& operator=(const Subprocess&) = delete;
  Subprocess(Subprocess&& other) noexcept;
  Subprocess& operator=(Subprocess&& other) noexcept;

  // Spawns argv[0] via PATH. `with_stdin` also opens a pipe to the child's
  // stdin, which `pump` then feeds.
  bool start(const std::vector<std::string>& argv, bool with_stdin = false);

  // Streams stdout into `sink` until EOF while writing `input` to stdin.
  // poll()s both directions, so neither a full stdout pipe nor a full stdin
  // pipe can wedge the pair — the classic hang described in notes §10.
  bool pump(std::string_view input, const ChunkSink& sink);

  // Convenience for the common case of no stdin.
  bool read_all(const ChunkSink& sink) { return pump({}, sink); }

  // Reaps the child and returns its exit status, or -1 if it died by signal or
  // never started. Idempotent, and called by the destructor.
  int wait();

  const std::string& error() const { return error_; }

 private:
  bool fail(std::string_view what);
  void close_stdin();
  void close_fds();

  pid_t pid_ = -1;
  int out_fd_ = -1;
  int in_fd_ = -1;
  int status_ = -1;
  bool reaped_ = false;
  std::vector<char> buf_;
  std::string error_;
};

// Splits a byte stream into lines across chunk boundaries. The terminator is
// not included, and the view handed to the sink is valid only for that call.
//
// Separate from Subprocess because every git command pk runs is line-oriented,
// and because a stream splitter is worth testing without spawning anything.
class LineSplitter {
 public:
  using LineSink = std::function<void(std::string_view)>;

  void feed(std::string_view chunk, const LineSink& sink);
  void finish(const LineSink& sink);  // flushes a trailing unterminated line
  void reset() { carry_.clear(); }

 private:
  std::string carry_;
};

}  // namespace pk
