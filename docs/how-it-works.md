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

## Trees of processes

Freezing an app means freezing several processes, so the app gives each of them a scope of its own and passes all of them to one `systemctl --user freeze` call. A browser tree of thirty processes therefore costs thirty moves, one freeze and one thaw, not thirty of each.

The tree is rebuilt from a live `/proc` scan rather than remembered, so children that started or exited since the last refresh are handled the moment the freeze or the hotkey runs. The selected process is the root: everything below it in the scan is included.

If any scope fails, the scopes that did freeze are thawed again, so a failure never leaves half an app stopped.

## One row per app

The window does not draw the tree from the top. Every process in the session descends from `systemd`, so a tree rooted there is one row holding every process you have — including the window itself, which is exactly the row that must not be frozen. The manager is left out and its children become the top level, so the rows are the apps and session services you recognize.

A launcher can leave more than one root inside one app. Bubblewrap, which Flatpak uses, forks helpers that are reparented, so one Flatpak app can appear as several roots in the same scope. Roots sharing a systemd unit are gathered into a single row, named from the app's `.desktop` entry. The unit comes from the cgroup path: the first `.scope` or `.service` below the per-user manager, skipping the manager's own units and the login session.

A gathered row is frozen as a set of processes, and the saved target records the unit name instead of a PID, so the hotkey finds the app again after its processes have been replaced.

## Why the scope stays

The process keeps its own scope after it resumes. Moving processes between cgroups is the expensive part, so reusing the scope makes later freezes nearly free. systemd removes the scope when the process exits, and the app notices that the next time it reads the process list.

## The watchdog

The GUI owns the timer, which is a problem if the GUI dies while something is frozen: the timer dies with it and the process would stay frozen forever.

So each freeze also starts a small detached process that runs `systemctl --user thaw` on its own. One watchdog covers every scope of the freeze, so a tree still needs only one. It is the `processfreezer.watchdog` module when you run from source, and the hidden `--watchdog` flag of the app in the prebuilt binary, which has no Python interpreter to start a module with. It starts counting only after `systemctl freeze` has returned, so the pause lasts the duration you asked for rather than that duration minus the time systemd spent applying the freeze.

The watchdog waits for a short token on its input before it starts counting; the app writes that token once the freeze has landed. If the app dies before that point, the pipe closes and the watchdog thaws immediately, instead of sleeping through a freeze that may or may not have happened.

It is killed when the app thaws the process normally. Closing the window also thaws everything the app froze, and terminates the matching watchdogs.

## One instance

A `QLocalServer` socket named after your user ID keeps a single copy running. Starting the app a second time finds the socket, asks the first instance to raise its window, and exits. A global hotkey registered by two instances would fight over the same key, so this is not just a convenience.

## Limits worth knowing

- Freezing an app takes each process of its tree into a scope of its own, so the app's processes end up spread over several scopes. The tree is read at the moment of the freeze: a child that starts a moment later is not in it until you freeze again.
- Applications packaged as Flatpak already run inside a per-application scope (`app-flatpak-<app-id>-<instance>.scope`). Freezing such an app moves its processes out into the app's own scopes, with the same caveat as above.
- The timer is wall-clock. Suspending the machine during a freeze pauses the countdown.
- Freezing a process that holds a lock another process is waiting for will stall that other process too. That is the system working as intended, not a bug.
