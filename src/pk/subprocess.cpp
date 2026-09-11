#include "pk/subprocess.hpp"

#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <mutex>
#include <poll.h>
#include <signal.h>
#include <spawn.h>
#include <sys/wait.h>
#include <unistd.h>
#include <utility>

extern char** environ;

namespace pk {
namespace {

constexpr std::size_t kReadBuffer = 1 << 18;  // 256 KB, per notes §10

// A child that exits while we are still feeding its stdin would otherwise take
// this process down with SIGPIPE. We want to see the EPIPE and carry on.
void ignore_sigpipe_once() {
  static std::once_flag once;
  std::call_once(once, [] { ::signal(SIGPIPE, SIG_IGN); });
}

bool set_nonblocking(int fd) {
  const int flags = ::fcntl(fd, F_GETFL, 0);
  return flags != -1 && ::fcntl(fd, F_SETFL, flags | O_NONBLOCK) != -1;
}

}  // namespace

Subprocess::~Subprocess() {
  close_fds();
  wait();
}

Subprocess::Subprocess(Subprocess&& other) noexcept { *this = std::move(other); }

Subprocess& Subprocess::operator=(Subprocess&& other) noexcept {
  if (this != &other) {
    close_fds();
    wait();
    pid_ = other.pid_;
    out_fd_ = other.out_fd_;
    in_fd_ = other.in_fd_;
    status_ = other.status_;
    reaped_ = other.reaped_;
    buf_ = std::move(other.buf_);
    error_ = std::move(other.error_);
    other.pid_ = -1;
    other.out_fd_ = -1;
    other.in_fd_ = -1;
    other.reaped_ = true;
  }
  return *this;
}

bool Subprocess::fail(std::string_view what) {
  error_.assign(what);
  if (errno != 0) {
    error_ += ": ";
    error_ += std::strerror(errno);
  }
  return false;
}

void Subprocess::close_stdin() {
  if (in_fd_ >= 0) {
    ::close(in_fd_);
    in_fd_ = -1;
  }
}

void Subprocess::close_fds() {
  close_stdin();
  if (out_fd_ >= 0) {
    ::close(out_fd_);
    out_fd_ = -1;
  }
}

bool Subprocess::start(const std::vector<std::string>& argv, bool with_stdin) {
  if (argv.empty()) {
    errno = 0;
    return fail("empty argv");
  }
  if (pid_ != -1) {
    errno = 0;
    return fail("already started");
  }
  ignore_sigpipe_once();

  int out_pipe[2];
  if (::pipe(out_pipe) != 0) return fail("pipe");
  int in_pipe[2] = {-1, -1};
  if (with_stdin && ::pipe(in_pipe) != 0) {
    ::close(out_pipe[0]);
    ::close(out_pipe[1]);
    return fail("pipe");
  }

  posix_spawn_file_actions_t actions;
  ::posix_spawn_file_actions_init(&actions);
  ::posix_spawn_file_actions_adddup2(&actions, out_pipe[1], STDOUT_FILENO);
  ::posix_spawn_file_actions_addclose(&actions, out_pipe[0]);
  if (out_pipe[1] != STDOUT_FILENO) {
    ::posix_spawn_file_actions_addclose(&actions, out_pipe[1]);
  }
  if (with_stdin) {
    ::posix_spawn_file_actions_adddup2(&actions, in_pipe[0], STDIN_FILENO);
    ::posix_spawn_file_actions_addclose(&actions, in_pipe[1]);
    if (in_pipe[0] != STDIN_FILENO) {
      ::posix_spawn_file_actions_addclose(&actions, in_pipe[0]);
    }
  }

  std::vector<char*> cargv;
  cargv.reserve(argv.size() + 1);
  for (const std::string& arg : argv) cargv.push_back(const_cast<char*>(arg.c_str()));
  cargv.push_back(nullptr);

  pid_t pid = -1;
  const int rc = ::posix_spawnp(&pid, cargv[0], &actions, nullptr, cargv.data(), environ);
  ::posix_spawn_file_actions_destroy(&actions);

  // The parent must drop its copy of the write end, or the read loop never
  // sees EOF and hangs forever (notes §10).
  ::close(out_pipe[1]);
  if (with_stdin) ::close(in_pipe[0]);

  if (rc != 0) {
    ::close(out_pipe[0]);
    if (with_stdin) ::close(in_pipe[1]);
    errno = rc;
    return fail("cannot run " + argv[0]);
  }

  pid_ = pid;
  reaped_ = false;
  out_fd_ = out_pipe[0];
  in_fd_ = with_stdin ? in_pipe[1] : -1;
  return true;
}

bool Subprocess::pump(std::string_view input, const ChunkSink& sink) {
  if (out_fd_ < 0) {
    errno = 0;
    return fail("not started");
  }
  buf_.resize(kReadBuffer);
  if (in_fd_ >= 0) {
    if (input.empty()) {
      close_stdin();  // let the child see EOF immediately
    } else if (!set_nonblocking(in_fd_)) {
      return fail("fcntl");
    }
  }

  std::size_t written = 0;
  while (out_fd_ >= 0) {
    struct pollfd fds[2];
    fds[0] = {out_fd_, POLLIN, 0};
    int nfds = 1;
    if (in_fd_ >= 0) {
      fds[1] = {in_fd_, POLLOUT, 0};
      nfds = 2;
    }
    if (::poll(fds, static_cast<nfds_t>(nfds), -1) < 0) {
      if (errno == EINTR) continue;
      return fail("poll");
    }

    // Drain stdout first: that is what lets the child make progress.
    if (fds[0].revents != 0) {
      const ssize_t got = ::read(out_fd_, buf_.data(), buf_.size());
      if (got < 0) {
        if (errno == EINTR || errno == EAGAIN) continue;
        return fail("read");
      }
      if (got == 0) {
        ::close(out_fd_);
        out_fd_ = -1;
        break;
      }
      sink(std::string_view(buf_.data(), static_cast<std::size_t>(got)));
    }

    if (nfds == 2 && fds[1].revents != 0) {
      const ssize_t put = ::write(in_fd_, input.data() + written, input.size() - written);
      if (put < 0) {
        if (errno == EINTR || errno == EAGAIN) continue;
        if (errno != EPIPE) return fail("write");
        close_stdin();  // the child stopped reading; it may still have output
      } else {
        written += static_cast<std::size_t>(put);
        if (written == input.size()) close_stdin();
      }
    }
  }
  return true;
}

int Subprocess::wait() {
  if (pid_ == -1 || reaped_) return status_;
  int raw = 0;
  while (::waitpid(pid_, &raw, 0) < 0) {
    if (errno != EINTR) {
      reaped_ = true;
      fail("waitpid");
      return -1;
    }
  }
  reaped_ = true;
  status_ = WIFEXITED(raw) ? WEXITSTATUS(raw) : -1;
  return status_;
}

void LineSplitter::feed(std::string_view chunk, const LineSink& sink) {
  while (!chunk.empty()) {
    const std::size_t nl = chunk.find('\n');
    if (nl == std::string_view::npos) {
      carry_.append(chunk);
      return;
    }
    if (carry_.empty()) {
      sink(chunk.substr(0, nl));
    } else {
      carry_.append(chunk.substr(0, nl));
      sink(carry_);
      carry_.clear();
    }
    chunk.remove_prefix(nl + 1);
  }
}

void LineSplitter::finish(const LineSink& sink) {
  if (!carry_.empty()) {
    sink(carry_);
    carry_.clear();
  }
}

}  // namespace pk
