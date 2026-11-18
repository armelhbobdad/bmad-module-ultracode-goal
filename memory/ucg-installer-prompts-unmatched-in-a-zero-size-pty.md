---
created: "2026-09-29 11:22"
session: "32c0ba1b-6b80-4f30-bf50-a7a5a6ac2c6d"
---

# UCG installer prompts unmatched in a zero-size pty

`npx github:armelhbobdad/bmad-module-ultracode-goal#main install` takes no non-interactive flags (`tools/cli/commands/install.js` declares `options: []`), so installing into a scratch project from an agent session means driving its clack prompts (project name, learning material, UCG awareness, and on a re-install "What would you like to do?") through a pty. A pty left at zero columns wraps the prompt text one character per line, the driver never matches a prompt, and the installer hangs until killed. Set a window size before spawning, e.g. `fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 50, 160, 0, 0))`, which let the rerun answer every prompt.
