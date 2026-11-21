# How freezing works

Process Freezer uses the freezer built into cgroup v2. It does not send signals, so a frozen process is genuinely suspended: it uses no CPU, keeps its memory, and picks up exactly where it stopped when thawed.

## The problem with /proc

A process cannot be frozen through `/proc`. The freezer is a property of a *cgroup*, and a cgroup is frozen as a whole. Moving one process out of its current cgroup and into one of its own is the only way to freeze it without taking its neighbours down with it.

That is what the first freeze does. The app asks systemd, over D-Bus, to create a transient scope for the selected PID:

```
busctl --user call org.freedesktop.systemd1 /org/freedesktop/systemd1 \
  org.freedesktop.systemd1.Manager StartTransientUnit \
  ssa(sv)a(sa(sv)) process-freezer-<pid>-<start>.scope fail 2 \
  Description s "Process Freezer target <name> (<pid>)" PIDs au 1 <pid> 0
```

The scope name includes the process start time, so it is unique per process lifetime. The app waits until `/proc/<pid>/cgroup` reports the new scope before freezing, because systemd answers before the move has landed.

Freezing and thawing then go through `systemctl --user freeze <scope>` and `systemctl --user thaw <scope>`, which are thin wrappers over the same D-Bus methods.

## Why the scope stays

The process keeps its own scope after it resumes. Moving processes between cgroups is the expensive part, so reusing the scope makes later freezes nearly free. systemd removes the scope when the process exits, and the app notices that the next time it reads the process list.

## The watchdog

The GUI owns the timer, which is a problem if the GUI dies while something is frozen: the timer dies with it and the process would stay frozen forever.

So each freeze also starts a small detached Python process that runs `systemctl --user thaw` on its own. It starts counting only after `systemctl freeze` has returned, so the pause lasts the duration you asked for rather than that duration minus the time systemd spent applying the freeze.

The watchdog waits for a short token on its input before it starts counting; the app writes that token once the freeze has landed. If the app dies before that point, the pipe closes and the watchdog thaws immediately, instead of sleeping through a freeze that may or may not have happened.

It is killed when the app thaws the process normally. Closing the window also thaws everything the app froze, and terminates the matching watchdogs.

Closing the window also thaws everything the app froze, and terminates the matching watchdogs.

## One instance

A `QLocalServer` socket named after your user ID keeps a single copy running. Starting the app a second time finds the socket, asks the first instance to raise its window, and exits. A global hotkey registered by two instances would fight over the same key, so this is not just a convenience.

## Limits worth knowing

- Only the selected process moves into the scope. Child processes stay where they are, so freezing a shell does not freeze its children, and freezing a browser's helper process does not freeze the browser.
- Applications packaged as Flatpak already run inside a per-application scope (`app-flatpak-<app-id>-<instance>.scope`). Freezing such an app moves only the chosen PID out, with the same caveat as above.
- The timer is wall-clock. Suspending the machine during a freeze pauses the countdown.
- Freezing a process that holds a lock another process is waiting for will stall that other process too. That is the system working as intended, not a bug.
