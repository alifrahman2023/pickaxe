"""Development-only ordered Git bridge; no product acceleration or eligibility."""
import subprocess


def ordered_replay(run_git, needle, scope, candidates):
    """Verify one prepared subsequence in one formatting session (or no process)."""
    if not needle:
        raise ValueError('empty needle')
    wanted = set(candidates)
    if candidates != [commit for commit in scope if commit in wanted]:
        raise ValueError('candidates must be a duplicate-free subsequence of current scope')
    if any(len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit)
           for commit in candidates):
        raise ValueError('fixture replay requires full SHA-1 object IDs')
    # Empty --stdin can select implicit HEAD. Never launch that Git command.
    if not candidates:
        return subprocess.CompletedProcess([], 0, b'', b'')
    return run_git('--no-pager', 'log', '--no-walk=unsorted', '--stdin',
                   b'-S' + needle, '--',
                   input=''.join(commit + '\n' for commit in candidates).encode('ascii'))
