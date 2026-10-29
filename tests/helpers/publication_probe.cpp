// Disposable macOS experiment for #22. Not linked into or installed with pk.
#include <cerrno>
#include <cstring>
#include <iostream>
#include <string>
#include <string_view>

#include <fcntl.h>
#include <sys/file.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

namespace {

class Descriptor {
public:
    explicit Descriptor(int fd) : fd_(fd) {}
    ~Descriptor() { if (fd_ >= 0) ::close(fd_); }
    Descriptor(const Descriptor&) = delete;
    Descriptor& operator=(const Descriptor&) = delete;
    int get() const { return fd_; }
    void close() {
        if (fd_ >= 0) ::close(fd_);
        fd_ = -1;
    }
private:
    int fd_;
};

struct Failure {
    const char* phase;
    int error;
    bool injected = false;
};

template <typename Operation>
auto step(const char* phase, Operation operation, std::string_view control = "") {
    if (control == phase) throw Failure{phase, EIO, true};
    const auto result = operation();
    if (result < 0) throw Failure{phase, errno};
    std::cout << phase << " ok" << std::endl;
    return result;
}

int publish(const std::string& resource, std::string_view control) {
    bool renamed = false;
    bool committed = false;
    try {
        const std::string current = resource + "/current";
        const std::string recovery = resource + "/recovery";
        Descriptor directory(step("open-directory", [&] {
            return ::open(resource.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        }));
        struct stat info {};
        // A leftover is evidence, even on initial installation. Never overwrite it.
        if (::lstat(recovery.c_str(), &info) == 0) throw Failure{"recovery-exists", EEXIST};
        if (errno != ENOENT) throw Failure{"inspect-recovery", errno};
        std::string replacement = resource + "/replacement-XXXXXX";
        Descriptor file(step("create-replacement", [&] { return ::mkstemp(replacement.data()); }));
        step("replacement-cloexec", [&] { return ::fcntl(file.get(), F_SETFD, FD_CLOEXEC); });
        constexpr std::string_view contents = "new generation\n";
        step("write", [&] {
            std::size_t written = 0;
            while (written < contents.size()) {
                const auto count = ::write(file.get(), contents.data() + written, contents.size() - written);
                if (count < 0) return -1;
                if (count == 0) { errno = EIO; return -1; }
                written += static_cast<std::size_t>(count);
            }
            return 0;
        });
        step("validate", [&] {
            char buffer[16] {};
            const auto count = ::pread(file.get(), buffer, sizeof(buffer), 0);
            if (count < 0) return -1;
            if (std::string_view(buffer, static_cast<std::size_t>(count)) != contents) {
                errno = EINVAL;
                return -1;
            }
            return 0;
        });
        step("replacement-fsync", [&] { return ::fsync(file.get()); });
        step("replacement-fullfsync", [&] { return ::fcntl(file.get(), F_FULLFSYNC); });
        bool previous = false;
        if (::lstat(current.c_str(), &info) == 0) {
            if (!S_ISREG(info.st_mode)) throw Failure{"current-type", EINVAL};
            previous = true;
            step("recovery-link", [&] { return ::link(current.c_str(), recovery.c_str()); });
        } else if (errno != ENOENT) {
            throw Failure{"inspect-current", errno};
        }
        step("directory-before-fsync", [&] { return ::fsync(directory.get()); });
        step("directory-before-fullfsync", [&] { return ::fcntl(directory.get(), F_FULLFSYNC); }, control);
        if (control == "pause-after-link") {
            std::cout << "checkpoint recovery-ready" << std::endl;
            if (std::cin.get() == EOF) throw Failure{"checkpoint-input", ECANCELED};
        }
        step("rename", [&] { return ::rename(replacement.c_str(), current.c_str()); });
        renamed = true;
        step("directory-after-fsync", [&] { return ::fsync(directory.get()); });
        // A real EBADF, deliberately triggered at the observation seam.
        if (control == "close-before-directory-after-fullfsync") directory.close();
        step("directory-after-fullfsync", [&] { return ::fcntl(directory.get(), F_FULLFSYNC); });
        committed = true;
        std::cout << "commit confirmed" << std::endl;
        if (previous) step("cleanup-unlink", [&] { return ::unlink(recovery.c_str()); }, control);
        step("directory-cleanup-fsync", [&] { return ::fsync(directory.get()); });
        step("directory-cleanup-fullfsync", [&] { return ::fcntl(directory.get(), F_FULLFSYNC); });
        std::cout << "state installed" << std::endl;
        return 0;
    } catch (const Failure& failure) {
        std::cout << "failure " << failure.phase << " errno " << failure.error
                  << (failure.injected ? " injected" : " actual") << std::endl;
        std::cerr << (committed ? "index installed; cleanup incomplete: " :
                      renamed ? "publication uncertain; retain recovery: " : "prior data preserved: ")
                  << failure.phase << ": " << std::strerror(failure.error) << '\n';
        std::cout << "state " << (committed ? "installed-cleanup-incomplete" :
                                  renamed ? "publication-uncertain" : "precommit-preserved") << std::endl;
        return committed ? 0 : 1;
    }
}

int git_helper(Descriptor& lock, const char* git) {
    int ready[2];
    if (::pipe(ready) != 0) return 1;
    Descriptor read_ready(ready[0]);
    Descriptor write_ready(ready[1]);
    if (::fcntl(write_ready.get(), F_SETFD, FD_CLOEXEC) != 0) return 1;
    const pid_t child = ::fork();
    if (child < 0) return 1;
    if (child == 0) {
        read_ready.close();
        // lock is O_CLOEXEC. On successful exec it closes without an unlock
        // operation that would also release the parent's shared lock ownership.
        ::execl(git, git, "hash-object", "--stdin", static_cast<char*>(nullptr));
        const int error = errno;
        (void)::write(write_ready.get(), &error, sizeof(error));
        ::_exit(126);
    }
    write_ready.close();
    int launch_error = 0;
    const auto count = ::read(read_ready.get(), &launch_error, sizeof(launch_error));
    lock.close();
    // EOF confirms exec closed the handshake FD. Git remains blocked on stdin.
    if (count == 0) std::cout << "helper " << child << std::endl;
    int status = 0;
    if (::waitpid(child, &status, 0) != child) return 1;
    return count == 0 && WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}

} // namespace

int main(int argc, char* argv[]) {
    if (argc < 3 || argc > 4) return 64;
    const std::string_view mode(argv[1]);
    const std::string resource(argv[2]);
    if (mode == "inspect") {
        struct statfs filesystem {};
        if (::statfs(resource.c_str(), &filesystem) != 0) return 1;
        std::cout << "filesystem " << filesystem.f_fstypename
                  << "\nlocal " << ((filesystem.f_flags & MNT_LOCAL) ? "yes" : "no")
                  << "\nmount " << filesystem.f_mntonname
                  << "\nsource " << filesystem.f_mntfromname
                  << "\nmount-flags " << filesystem.f_flags
                  << "\nF_FULLFSYNC " << F_FULLFSYNC << '\n';
        return 0;
    }
    const std::string_view control = argc == 4 ? argv[3] : "";
    if (mode != "publish" && mode != "hold-lock" && mode != "try-lock" && mode != "git-helper") return 64;
    if (mode == "publish" && control != "" && control != "pause-after-link"
        && control != "directory-before-fullfsync" && control != "cleanup-unlink"
        && control != "close-before-directory-after-fullfsync") return 64;
    Descriptor lock(::open((resource + "/writer.lock").c_str(), O_RDWR | O_CREAT | O_CLOEXEC, 0600));
    if (lock.get() < 0) return 1;
    if (::flock(lock.get(), LOCK_EX | LOCK_NB) != 0) {
        const int error = errno;
        std::cout << "lock " << (error == EWOULDBLOCK ? "busy" : "error") << std::endl;
        return error == EWOULDBLOCK ? 3 : 1;
    }
    std::cout << "lock acquired" << std::endl;
    if (mode == "hold-lock") {
        std::cin.get();
        return 0;
    }
    if (mode == "git-helper" && argc == 4) return git_helper(lock, argv[3]);
    if (mode == "publish") return publish(resource, control);
    return mode == "try-lock" ? 0 : 64;
}
